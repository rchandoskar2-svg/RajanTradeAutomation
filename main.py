# ============================================================
# RajanTradeAutomation - Main Backend (Render / Flask)
# Version: 5.0  (Bias% Threshold + Sector + Stock Engine + Signals Ready)
# Author: GPT-5 (For Rajan Chandoskar)
# ============================================================

from flask import Flask, request, jsonify
import requests
import os
import time
import threading

# ------------------------------------------------------------
# NSE CLIENT (nsetools) – For Nifty50 breadth + SectorPerf + stocks
# ------------------------------------------------------------
try:
    from nsetools import Nse
    NSE_CLIENT = Nse()
except Exception:
    NSE_CLIENT = None

app = Flask(__name__)

# ------------------------------------------------------------
# ENVIRONMENT VARIABLES  (Render → Environment)
# ------------------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY", "").strip()
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

# Rajan ने सांगितले → INTERVAL_SECS = 1800 (30 minutes)
INTERVAL_SECS = int(os.getenv("INTERVAL_SECS", "1800"))

MODE = os.getenv("MODE", "PAPER").upper()


# ------------------------------------------------------------
# COMMON HELPER → WebApp.gs ला JSON POST
# ------------------------------------------------------------
def call_webapp(action, payload=None, timeout=15):
    if payload is None:
        payload = {}

    if not WEBAPP_URL:
        return {"ok": False, "error": "WEBAPP_URL missing"}

    body = {"action": action, "payload": payload}

    try:
        res = requests.post(WEBAPP_URL, json=body, timeout=timeout)
        try:
            return res.json()
        except:
            return {"ok": True, "raw": res.text}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ------------------------------------------------------------
# BASIC ROUTES
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def root():
    return "RajanTradeAutomation backend LIVE ⭐ v5.0", 200


@app.route("/ping", methods=["GET"])
def ping():
    return "PONG", 200


# ------------------------------------------------------------
# GET SETTINGS (Render → Sheets)
# ------------------------------------------------------------
@app.route("/getSettings", methods=["GET"])
def get_settings():
    return jsonify(call_webapp("getSettings", {}))


# ------------------------------------------------------------
# FYERS AUTH REDIRECT  (unchanged)
# ------------------------------------------------------------
@app.route("/fyers-redirect", methods=["GET"])
def fyers_redirect():
    status = request.args.get("s") or request.args.get("status", "")
    auth_code = request.args.get("auth_code", "")
    state = request.args.get("state", "")

    html = f"""
    <h2>Fyers Redirect Handler</h2>
    <p>Status: <b>{status}</b></p>
    <p>State: <b>{state}</b></p>
    <p><b>Auth Code (save safely):</b></p>
    <textarea rows="5" cols="100">{auth_code}</textarea>
    <p>Use this auth_code to generate FYERS_ACCESS_TOKEN.</p>
    """
    return html, 200


# ============================================================
#                     SECTOR MAP (Fixed)
# ============================================================
SECTOR_INDEX_MAP = {
    "NIFTY BANK": "BANK",
    "NIFTY PSU BANK": "PSUBANK",
    "NIFTY OIL & GAS": "OILGAS",
    "NIFTY IT": "IT",
    "NIFTY PHARMA": "PHARMA",
    "NIFTY AUTO": "AUTO",
    "NIFTY FMCG": "FMCG",
    "NIFTY METAL": "METAL",
    "NIFTY FIN SERVICE": "FIN",
    "NIFTY REALTY": "REALTY",
    "NIFTY MEDIA": "MEDIA",
}


# ============================================================
#              Rajan Requirement → Bias % Threshold
# ============================================================
def compute_bias_with_threshold(adv, dec, threshold_percent):
    """
    Rajan Rule:
    BUY bias → advances >= threshold%
    SELL bias → declines >= threshold%
    NEUTRAL otherwise
    """
    total = adv + dec
    if total <= 0:
        return "NEUTRAL"

    adv_pct = (adv / total) * 100
    dec_pct = (dec / total) * 100

    if adv_pct >= threshold_percent:
        return "BUY"
    if dec_pct >= threshold_percent:
        return "SELL"

    return "NEUTRAL"


# ============================================================
#                   NSE → Nifty50 Breadth
# ============================================================
def get_nifty50_breadth():
    if NSE_CLIENT is None:
        return {"ok": False, "error": "nsetools not available"}

    try:
        q = NSE_CLIENT.get_index_quote("NIFTY 50")
        return {
            "ok": True,
            "advances": int(q.get("advances", 0)),
            "declines": int(q.get("declines", 0)),
            "unchanged": int(q.get("unchanged", 0)),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ============================================================
#                   Fetch Sector Quotes
# ============================================================
def fetch_all_sector_quotes():
    if NSE_CLIENT is None: 
        return []

    try:
        all_idx = NSE_CLIENT.get_all_index_quote()
    except:
        return []

    rows = []
    for item in all_idx:
        name = item.get("index") or item.get("indexSymbol")
        if not name or name not in SECTOR_INDEX_MAP:
            continue

        rows.append({
            "sector_name": name,
            "sector_code": SECTOR_INDEX_MAP[name],
            "%chg": float(item.get("percentChange", 0.0)),
            "advances": int(item.get("advances", 0)),
            "declines": int(item.get("declines", 0))
        })

    return rows


# ============================================================
#            Sort sectors + pick top ones (Rajan Rules)
# ============================================================
def pick_top_sectors(sectors, bias, settings):
    if not sectors:
        return [], set()

    if bias == "SELL":
        sorted_list = sorted(sectors, key=lambda x: x["%chg"])
        top_n = int(settings.get("SELL_SECTOR_COUNT", 2))
    else:
        sorted_list = sorted(sectors, key=lambda x: x["%chg"], reverse=True)
        top_n = int(settings.get("BUY_SECTOR_COUNT", 2))

    top_n = max(1, top_n)
    top = sorted_list[:top_n]
    names = {x["sector_name"] for x in top}

    return sorted_list, names


# ============================================================
#                Fetch Stocks for selected sectors
# ============================================================
def fetch_stocks_for_top_sectors(top_names, bias, settings):
    if NSE_CLIENT is None:
        return []

    max_up = float(settings.get("MAX_UP_PERCENT", 2.5))
    max_down = float(settings.get("MAX_DOWN_PERCENT", -2.5))

    rows = []

    for sec in top_names:
        try:
            quotes = NSE_CLIENT.get_stock_quote_in_index(index=sec, include_index=False)
        except:
            continue

        for q in quotes:
            sym = q.get("symbol")
            if not sym:
                continue

            pchg = float(q.get("pChange", 0.0) or 0.0)
            ltp = float(q.get("ltp", 0.0) or 0.0)
            vol = int(q.get("totalTradedVolume", 0))

            selected = False
            if bias == "BUY":
                if pchg > 0 and pchg <= max_up:
                    selected = True
            elif bias == "SELL":
                if pchg < 0 and pchg >= max_down:
                    selected = True

            rows.append({
                "symbol": f"NSE:{sym}-EQ",
                "direction_bias": bias,
                "sector": sec,
                "%chg": pchg,
                "ltp": ltp,
                "volume": vol,
                "selected": selected
            })

    return rows


# ============================================================
#                ONE FULL ENGINE CYCLE
# ============================================================
def run_engine_once(settings, push_to_sheets=True):
    # 1) Breadth
    breadth = get_nifty50_breadth()
    if not breadth.get("ok"):
        return breadth

    adv = breadth["advances"]
    dec = breadth["declines"]

    # Rajan rule – editable threshold%
    threshold = float(settings.get("BIAS_THRESHOLD_PERCENT", 60))

    bias = compute_bias_with_threshold(adv, dec, threshold)

    # 2) Sector sorting
    sector_rows = fetch_all_sector_quotes()
    sorted_sectors, top_sector_names = pick_top_sectors(sector_rows, bias, settings)

    # 3) Stock selection
    stocks = fetch_stocks_for_top_sectors(top_sector_names, bias, settings)

    # 4) Push to Sheets
    if push_to_sheets:
        call_webapp("updateSectorPerf", {"sectors": sorted_sectors})
        call_webapp("updateStockList", {"stocks": stocks})

    return {
        "ok": True,
        "bias": bias,
        "advances": adv,
        "declines": dec,
        "threshold": threshold,
        "sectors_count": len(sorted_sectors),
        "top_sectors": list(top_sector_names),
        "stocks_count": len(stocks)
    }


# ============================================================
#             Background THREAD ENGINE (Every 1800 sec)
# ============================================================
def engine_cycle():
    while True:
        try:
            print("🔄 ENGINE CYCLE STARTED")

            settings_resp = call_webapp("getSettings", {})
            settings = settings_resp.get("settings", {}) if isinstance(settings_resp, dict) else {}

            result = run_engine_once(settings)
            print("⚙ Result:", result)

        except Exception as e:
            print("❌ ENGINE ERROR:", e)

        time.sleep(INTERVAL_SECS)   # 1800 seconds


def start_engine():
    t = threading.Thread(target=engine_cycle, daemon=True)
    t.start()


start_engine()


# ============================================================
#                   DEBUG ROUTE (No Sheets Write)
# ============================================================
@app.route("/engine/debug", methods=["GET"])
def engine_debug():
    settings_resp = call_webapp("getSettings", {})
    settings = settings_resp.get("settings", {}) if isinstance(settings_resp, dict) else {}
    return jsonify(run_engine_once(settings, push_to_sheets=False))


# ============================================================
#                     TEST ROUTES (UNCHANGED)
# ============================================================
# ... (Your test routes remain unchanged here)
# ============================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
