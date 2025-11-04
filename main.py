# main.py
import os, json, time
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ---- ENV (Render Dashboard मध्ये set करा) ----
WEBAPP_EXEC_URL = os.getenv("WEBAPP_EXEC_URL")  # तुमचा Google Apps Script WebApp (exec) URL
APP_NAME = "RajanTradeAutomation"

# ---------- Helpers ----------
def gs_post(payload: dict):
    """Call Google Apps Script WebApp with JSON."""
    assert WEBAPP_EXEC_URL, "WEBAPP_EXEC_URL not configured"
    r = requests.post(WEBAPP_EXEC_URL, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()

def get_settings():
    """Fetch key-value settings from Google Sheet via WebApp."""
    res = gs_post({"action": "get_settings"})
    # अपेक्षित: {"ok": True, "settings": {"LOW_WINDOW_START":"09:15", ...}}
    if not res.get("ok"):
        raise RuntimeError(f"Settings fetch failed: {res}")
    st = res["settings"]
    # Normalize numeric
    def as_int(k, default=0): return int(str(st.get(k, default)).strip())
    def as_float(k, default=0.0): return float(str(st.get(k, default)).strip())

    settings = {
        "LOW_WINDOW_START": st.get("LOW_WINDOW_START", "09:15"),
        "LOW_WINDOW_END":   st.get("LOW_WINDOW_END", "09:30"),
        "TOTAL_BUY":        as_int("TOTAL_BUY", 15),
        "ALERT1_MAX":       as_int("ALERT1_MAX", 7),
        "ALERT2_MAX":       as_int("ALERT2_MAX", 8),
        "CAPITAL":          as_float("CAPITAL", 500000),
        "SORT_BY":          st.get("SORT_BY", "volume").lower(),  # "volume" | "%change"
    }
    return settings

def parse_chartink_payload(data):
    """
    Try to extract stocks with volume and optional %change + meta.
    Accepts flexible Chartink webhook shapes.
    Output: dict(alert_stage, scanner_name, scanner_url, items=[{symbol, volume, pchange}])
    """
    # 1) Alert stage
    alert_stage = data.get("alert_stage") or data.get("stage") or data.get("ALERT_STAGE") or 1
    try: alert_stage = int(alert_stage)
    except: alert_stage = 1

    # 2) Scanner meta (if available)
    scanner_name = data.get("scanner_name") or data.get("scan_name") or ""
    scanner_url  = data.get("scanner_url") or data.get("scan_url") or ""

    # 3) Stock list (handle multiple possible keys)
    raw = data.get("stocks") or data.get("data") or data.get("results") or []
    if isinstance(raw, str):
        # "TCS,INFY,HDFCBANK" → split
        raw = [s.strip() for s in raw.split(",") if s.strip()]

    items = []
    for row in raw:
        if isinstance(row, str):
            sym = row.strip().upper()
            items.append({"symbol": sym, "volume": 0.0, "pchange": 0.0})
        elif isinstance(row, dict):
            sym = (row.get("symbol") or row.get("name") or row.get("nsecode") or "").upper()
            vol = row.get("volume") or row.get("vol") or row.get("traded_qty") or 0
            chg = row.get("pchange") or row.get("%change") or row.get("change_perc") or 0.0
            try: vol = float(vol)
            except: vol = 0.0
            try: chg = float(chg)
            except: chg = 0.0
            if sym:
                items.append({"symbol": sym, "volume": vol, "pchange": chg})

    # dedupe by symbol (keep max volume)
    seen = {}
    for it in items:
        s = it["symbol"]
        if s not in seen or it["volume"] > seen[s]["volume"]:
            seen[s] = it
    items = list(seen.values())

    return {
        "alert_stage": alert_stage,
        "scanner_name": scanner_name,
        "scanner_url": scanner_url,
        "items": items,
    }

def rank_and_select(items, settings, alert_stage):
    """Apply ranking by volume (or %change) and enforce caps."""
    total_buy = settings["TOTAL_BUY"]
    a1max     = settings["ALERT1_MAX"]
    a2max     = settings["ALERT2_MAX"]
    sort_by   = settings["SORT_BY"]  # "volume" | "%change"

    # Decide phase cap
    # Default: 50-50 split between stages; if TOTAL_BUY fits in A1, take all in A1 and skip A2.
    if alert_stage == 1:
        max_n = min(a1max, total_buy)
        phase_cap_ratio = 1.0 if total_buy <= a1max else 0.5
    else:
        if total_buy <= a1max:
            return {"skip": True, "reason": "TOTAL_BUY fulfilled in Alert1"}
        remaining = max(total_buy - a1max, 0)
        max_n = min(a2max, remaining)
        phase_cap_ratio = 0.5

    # Rank
    key = (lambda x: x["volume"]) if sort_by == "volume" else (lambda x: x["pchange"])
    ranked = sorted(items, key=key, reverse=True)

    # Select
    if len(ranked) > max_n:
        selected = ranked[:max_n]
        truncated = True
    else:
        selected = ranked
        truncated = False

    return {
        "skip": False,
        "selected": selected,
        "truncated": truncated,
        "max_n": max_n,
        "phase_cap_ratio": phase_cap_ratio,
    }

def rupees(n):  # simple money format
    return f"₹{int(round(n, 0)):,}".replace(",", ",")

# ---------- Routes ----------
@app.get("/health")
def health():
    return jsonify({"ok": True, "app": APP_NAME, "ts": int(time.time())})

@app.post("/chartink-alert")
def chartink_alert():
    try:
        data = request.get_json(force=True, silent=False) or {}
        parsed = parse_chartink_payload(data)
        alert_stage = parsed["alert_stage"]

        settings = get_settings()
        sel = rank_and_select(parsed["items"], settings, alert_stage)

        if sel.get("skip"):
            # Notify sheet/logs that stage-2 skipped (if needed)
            gs_post({
                "action": "phase22_notify_skip",
                "payload": {
                    "alert_stage": alert_stage,
                    "reason": sel["reason"],
                    "scanner_name": parsed["scanner_name"],
                    "scanner_url": parsed["scanner_url"],
                }
            })
            return jsonify({"ok": True, "skipped": True, "reason": sel["reason"]})

        selected = sel["selected"]
        if not selected:
            return jsonify({"ok": True, "selected": [], "note": "No symbols in alert"})

        capital = settings["CAPITAL"]
        phase_cap = capital * sel["phase_cap_ratio"]
        per_stock_alloc = phase_cap / max(len(selected), 1)

        # Prepare payload for WebApp/Sheets
        payload = {
            "alert_stage": alert_stage,
            "scanner_name": parsed["scanner_name"],
            "scanner_url": parsed["scanner_url"],
            "total_buy": settings["TOTAL_BUY"],
            "alert1_max": settings["ALERT1_MAX"],
            "alert2_max": settings["ALERT2_MAX"],
            "capital_total": capital,
            "phase_capital": phase_cap,
            "per_stock_alloc": per_stock_alloc,
            "sort_by": settings["SORT_BY"],
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
            "max_n": sel["max_n"],
        }

        # Update Google Sheets (StockList + Logs + Telegram summary)
        res = gs_post({"action": "phase22_selection", "payload": payload})

        return jsonify({"ok": True, "sheet": res, "selected_count": len(selected)})

    except Exception as e:
        # Send error to WebApp Logs + Telegram
        try:
            gs_post({"action": "phase22_error", "message": str(e)})
        except:  # if even that fails, just return
            pass
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
