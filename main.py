# ============================================================
# RajanTradeAutomation - Main Backend (Render / Flask)
# Version: 4.2 (Historical Candle Only – LOCKED)
# ============================================================

from flask import Flask, request, jsonify
import requests
import os
import time
import threading
from datetime import datetime, timedelta
import pytz

# ------------------------------------------------------------
# NSE CLIENT (unchanged)
# ------------------------------------------------------------
try:
    from nsetools import Nse
    NSE_CLIENT = Nse()
except Exception:
    NSE_CLIENT = None

app = Flask(__name__)

# ------------------------------------------------------------
# ENVIRONMENT VARIABLES
# ------------------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
FYERS_HISTORICAL_URL = os.getenv(
    "FYERS_HISTORICAL_URL",
    "https://api.fyers.in/data-rest/v2/history"
).strip()

INTERVAL_SECS = int(os.getenv("INTERVAL_SECS", "60"))

IST = pytz.timezone("Asia/Kolkata")

# ------------------------------------------------------------
# COMMON HELPER → CALL WebApp.gs
# ------------------------------------------------------------
def call_webapp(action, payload=None, timeout=20):
    if payload is None:
        payload = {}
    body = {"action": action, "payload": payload}
    try:
        r = requests.post(WEBAPP_URL, json=body, timeout=timeout)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ------------------------------------------------------------
# ROOT + HEALTH
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def root():
    return "RajanTradeAutomation backend LIVE (Historical Candle Test)", 200

@app.route("/ping", methods=["GET"])
def ping():
    return "PONG", 200

# ============================================================
# HISTORICAL CANDLE LOGIC (LOCKED)
# ============================================================

def fetch_915_to_930_candles(symbol):
    """
    Fetch exactly 3 completed 5-min candles:
    09:15–09:20
    09:20–09:25
    09:25–09:30
    """
    today = datetime.now(IST).strftime("%Y-%m-%d")

    start_dt = IST.localize(datetime.strptime(today + " 09:15", "%Y-%m-%d %H:%M"))
    end_dt   = IST.localize(datetime.strptime(today + " 09:30", "%Y-%m-%d %H:%M"))

    params = {
        "symbol": symbol,
        "resolution": "5",
        "date_format": "1",
        "range_from": start_dt.strftime("%Y-%m-%d"),
        "range_to": end_dt.strftime("%Y-%m-%d"),
        "cont_flag": "1"
    }

    headers = {
        "Authorization": f"Bearer {FYERS_ACCESS_TOKEN}"
    }

    r = requests.get(FYERS_HISTORICAL_URL, params=params, headers=headers, timeout=15)
    data = r.json()

    candles = data.get("candles", [])

    out = []
    for c in candles:
        ts = datetime.fromtimestamp(c[0], IST)
        if start_dt <= ts < end_dt:
            out.append({
                "symbol": symbol,
                "time": ts.isoformat(),
                "timeframe": "5m",
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": c[5],
                "candle_index": 0,
                "lowest_volume_so_far": c[5],
                "is_signal": False,
                "direction": ""
            })

    return out[:3]  # safety lock

def push_historical_915(symbol):
    candles = fetch_915_to_930_candles(symbol)

    if len(candles) != 3:
        print("⚠ Expected 3 candles, got:", len(candles))
        return

    call_webapp("pushCandle", {"candles": candles})
    print("✅ Historical candles (09:15–09:30) pushed")

# ------------------------------------------------------------
# ONE-TIME TEST ROUTE
# ------------------------------------------------------------
@app.route("/test/historical-915", methods=["GET"])
def test_historical_915():
    symbol = "NSE:SBIN-EQ"   # test symbol only
    push_historical_915(symbol)
    return jsonify({"ok": True, "symbol": symbol})

# ------------------------------------------------------------
# ENGINE LOOP (NO STRATEGY, NO LIVE)
# ------------------------------------------------------------
def engine_cycle():
    while True:
        try:
            print("⏳ Engine idle (historical test mode)")
        except Exception as e:
            print("Engine error:", e)
        time.sleep(INTERVAL_SECS)

def start_engine():
    t = threading.Thread(target=engine_cycle, daemon=True)
    t.start()

start_engine()

# ------------------------------------------------------------
# FLASK ENTRY
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
