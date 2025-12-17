# ============================================================
# RajanTradeAutomation – Main Backend
# ONLY Historical Candle Test (09:15–09:30, 5m, 3 candles)
# ============================================================

from flask import Flask, jsonify
import requests
import os
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)

# ------------------------------------------------------------
# ENV
# ------------------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

FYERS_HISTORY_URL = "https://api.fyers.in/data-rest/v2/history"

IST = pytz.timezone("Asia/Kolkata")

# ------------------------------------------------------------
# WebApp Caller
# ------------------------------------------------------------
def call_webapp(action, payload):
    body = {"action": action, "payload": payload}
    res = requests.post(WEBAPP_URL, json=body, timeout=20)
    try:
        return res.json()
    except:
        return {"raw": res.text}

# ------------------------------------------------------------
# FYERS Historical Fetch
# ------------------------------------------------------------
def fetch_915_candles(symbol):
    today = datetime.now(IST).date()

    from_dt = IST.localize(datetime.combine(today, datetime.strptime("09:15", "%H:%M").time()))
    to_dt   = IST.localize(datetime.combine(today, datetime.strptime("09:30", "%H:%M").time()))

    params = {
        "symbol": symbol,
        "resolution": "5",
        "date_format": "1",
        "range_from": from_dt.strftime("%Y-%m-%d"),
        "range_to": to_dt.strftime("%Y-%m-%d"),
        "cont_flag": "1"
    }

    headers = {
        "Authorization": f"Bearer {FYERS_ACCESS_TOKEN}"
    }

    r = requests.get(FYERS_HISTORY_URL, params=params, headers=headers)
    data = r.json()

    if data.get("s") != "ok":
        raise Exception(data)

    candles = data["candles"]

    result = []
    idx = 1
    for c in candles:
        ts = datetime.fromtimestamp(c[0], IST)
        if ts.strftime("%H:%M") in ["09:15", "09:20", "09:25"]:
            result.append({
                "symbol": symbol,
                "time": ts.isoformat(),
                "timeframe": "5m",
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": c[5],
                "candle_index": idx,
                "lowest_volume_so_far": c[5],
                "is_signal": False,
                "direction": ""
            })
            idx += 1

    return result

# ------------------------------------------------------------
# TEST ROUTE
# ------------------------------------------------------------
@app.route("/test/historical-915", methods=["GET"])
def test_historical_915():
    try:
        symbol = "NSE:SBIN-EQ"   # test symbol (change later)

        candles = fetch_915_candles(symbol)

        if len(candles) != 3:
            return jsonify({
                "ok": False,
                "error": "Expected 3 candles",
                "received": len(candles)
            })

        call_webapp("pushCandle", {"candles": candles})

        return jsonify({
            "ok": True,
            "candles_pushed": len(candles)
        })

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        })

# ------------------------------------------------------------
# ROOT
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def root():
    return "Historical Candle Engine READY", 200

# ------------------------------------------------------------
# START
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
