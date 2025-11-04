# ==========================
# RajanTradeAutomation : Phase 2.2 (Final)
# ==========================

import os, json, time, requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- Environment Variables (Render Dashboard मध्ये सेट केलेले) ---
WEBAPP_EXEC_URL = os.getenv("WEBAPP_EXEC_URL")
CHARTINK_TOKEN = os.getenv("CHARTINK_TOKEN", "")
APP_NAME = "RajanTradeAutomation"

# ==========================
# Helper Functions
# ==========================

def gs_post(payload: dict):
    """Call Google Apps Script WebApp (exec URL)"""
    if not WEBAPP_EXEC_URL:
        raise RuntimeError("WEBAPP_EXEC_URL not configured")
    r = requests.post(WEBAPP_EXEC_URL, json=payload, timeout=25)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {"ok": True}

def get_settings():
    """Fetch key-value from Google Sheet"""
    res = gs_post({"action": "get_settings"})
    if not res.get("ok"):
        raise RuntimeError("Settings fetch failed: " + str(res))
    st = res["settings"]

    def as_int(k, d=0): 
        try: return int(str(st.get(k, d)).strip())
        except: return d
    def as_float(k, d=0.0): 
        try: return float(str(st.get(k, d)).strip())
        except: return d

    return {
        "TOTAL_BUY": as_int("TOTAL_BUY", 15),
        "ALERT1_MAX": as_int("ALERT1_MAX", 7),
        "ALERT2_MAX": as_int("ALERT2_MAX", 8),
        "CAPITAL": as_float("CAPITAL", 500000),
        "SORT_BY": (st.get("SORT_BY") or "volume").lower(),
    }

def parse_chartink_payload(data):
    """Parse Chartink webhook into usable dict"""
    stage = data.get("alert_stage") or data.get("stage") or data.get("ALERT_STAGE") or 1
    try: stage = int(stage)
    except: stage = 1
    if stage not in [1, 2]:
        stage = 1

    name = data.get("scanner_name") or data.get("scan_name") or "Rocket Rajan Scanner"
    url = data.get("scanner_url") or data.get("scan_url") or "https://chartink.com/screener/rocket-rajan"
    raw = data.get("stocks") or data.get("data") or []

    if isinstance(raw, str):
        raw = [s.strip() for s in raw.split(",") if s.strip()]

    items = []
    for r in raw:
        if isinstance(r, str):
            items.append({"symbol": r.upper(), "volume": 0.0, "pchange": 0.0})
        elif isinstance(r, dict):
            sym = str(r.get("symbol") or r.get("name") or "").upper()
            vol = float(r.get("volume") or r.get("vol") or r.get("traded_qty") or 0)
            chg = float(r.get("pchange") or r.get("%change") or r.get("change") or 0)
            if sym:
                items.append({"symbol": sym, "volume": vol, "pchange": chg})
    return {"stage": stage, "scanner_name": name, "scanner_url": url, "items": items}

def rank_and_select(items, stg, sets):
    """Apply ranking + filtering rules"""
    total_buy = sets["TOTAL_BUY"]
    a1max = sets["ALERT1_MAX"]
    a2max = sets["ALERT2_MAX"]
    sort_by = sets["SORT_BY"]

    # Decide cap & allocation ratio
    if stg == 1:
        maxn = min(a1max, total_buy)
        ratio = 1.0 if total_buy <= a1max else 0.5
    else:
        if total_buy <= a1max:
            return {"skip": True, "reason": "TOTAL_BUY fulfilled in Alert1"}
        rem = max(total_buy - a1max, 0)
        maxn = min(a2max, rem)
        ratio = 0.5

    key = (lambda x: x["volume"]) if sort_by == "volume" else (lambda x: x["pchange"])
    ranked = sorted(items, key=key, reverse=True)

    if len(ranked) > maxn:
        selected = ranked[:maxn]
        truncated = True
    else:
        selected = ranked
        truncated = False

    return {
        "skip": False,
        "selected": selected,
        "truncated": truncated,
        "maxn": maxn,
        "ratio": ratio,
    }

# ==========================
# ROUTES
# ==========================

@app.get("/health")
def health():
    return jsonify({"ok": True, "app": APP_NAME, "ts": int(time.time())})

@app.route("/chartink-alert", methods=["POST", "GET"])
def chartink_alert():
    try:
        # ---- Verify token ----
        token = request.args.get("token")
        if token and CHARTINK_TOKEN and token != CHARTINK_TOKEN:
            return jsonify({"ok": False, "error": "Invalid token"}), 403

        data = request.get_json(force=True, silent=True) or {}
        parsed = parse_chartink_payload(data)
        stage = parsed["stage"]

        # ---- Fetch dynamic settings ----
        sets = get_settings()
        sel = rank_and_select(parsed["items"], stage, sets)

        if sel.get("skip"):
            gs_post({
                "action": "phase22_notify_skip",
                "payload": {
                    "alert_stage": stage,
                    "reason": sel["reason"],
                    "scanner_name": parsed["scanner_name"],
                    "scanner_url": parsed["scanner_url"]
                }
            })
            return jsonify({"ok": True, "skipped": True, "reason": sel["reason"]})

        selected = sel["selected"]
        if not selected:
            return jsonify({"ok": True, "note": "No symbols"}), 200

        capital = sets["CAPITAL"]
        phase_cap = capital * sel["ratio"]
        per_stock_alloc = phase_cap / max(len(selected), 1)

        payload = {
            "alert_stage": stage,
            "scanner_name": parsed["scanner_name"],
            "scanner_url": parsed["scanner_url"],
            "total_buy": sets["TOTAL_BUY"],
            "alert1_max": sets["ALERT1_MAX"],
            "alert2_max": sets["ALERT2_MAX"],
            "capital_total": capital,
            "phase_capital": phase_cap,
            "per_stock_alloc": per_stock_alloc,
            "sort_by": sets["SORT_BY"],
            "selected": [
                {
                    "rank": i+1,
                    "symbol": it["symbol"],
                    "volume": it["volume"],
                    "pchange": it["pchange"],
                    "alloc": per_stock_alloc
                } for i, it in enumerate(selected)
            ],
            "truncated": sel["truncated"],
            "max_n": sel["maxn"]
        }

        # ---- Update Google Sheets ----
        resp = gs_post({"action": "phase22_selection", "payload": payload})
        return jsonify({"ok": True, "stage": stage, "count": len(selected), "sheet": resp}), 200

    except Exception as e:
        try:
            gs_post({"action": "phase22_error", "message": str(e)})
        except Exception:
            pass
        return jsonify({"ok": False, "error": str(e)}), 500


# ==========================
# Entry
# ==========================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
