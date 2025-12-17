# ============================================================
# RajanTradeAutomation – Historical Candle Engine (LOCK STEP)
# Purpose: Fetch ONLY 3 candles (09:15–09:30, 5m)
# ============================================================

from flask import Flask, jsonify
import requests
import os
from datetime import datetime, time
from dateutil import tz

# ------------------------------------------------------------
# ENV
# ------------------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
FYERS_HISTORICAL_URL = "https://api.fyers.in/data-rest/v2/history"

IST = tz.gettz("Asia/Kolkata")

app = Flask(__name__)

# ------------------------------------------------------------
# Helper → call Google Sheets WebApp
# ------------------------------------------------------------
def call_webapp(action, payload):
    body = {"action": action, "payload": payload}
    res = requests.post(WEBAPP_URL, json=body, timeout=20)
    try:
        return res.json()
    except Exception:
        return {"ok": False, "raw": res.text}

# ------------------------------------------------------------
# Fetch historical candles (single symbol)
# ------------------------------------------------------------
def fetch_historical_915(symbol):
    today = datetime.now(IST).date()

    from_dt = datetime.combine(today, time(9, 15), IST)
    to_dt   = datetime.combine(today, time(9, 30), IST)

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

    r = requests.get(FYERS_HISTORICAL_URL, params=params, headers=headers, timeout=20)
    data = r.json()

    if data.get("s") != "ok":
        raise Exception(str(data))

    candles = data.get("candles", [])
    out = []

    idx = 1
    for c in candles:
        ts, o, h, l, cl, v = c
        t = datetime.fromtimestamp(ts, IST)

        # STRICT FILTER → only 09:15–09:30
        if t.time() < time(9, 15) or t.time() > time(9, 30):
            continue

        out.append({
            "symbol": symbol,
            "time": t.isoformat(),
            "timeframe": "5m",
            "open": o,
            "high": h,
            "low": l,
            "close": cl,
            "volume": v,
            "candle_index": idx,
            "lowest_volume_so_far": v,   # temp (strategy नंतर)
            "is_signal": False,
            "direction": ""
        })
        idx += 1

    return out[:3]   # HARD LOCK → only 3 candles

# ------------------------------------------------------------
# TEST ROUTE
# ------------------------------------------------------------
@app.route("/test/historical-915", methods=["GET"])
def test_historical():
    try:
        symbol = "NSE:SBIN-EQ"   # test symbol
        candles = fetch_historical_915(symbol)

        if not candles:
            return jsonify({"ok": False, "error": "No candles fetched"})

        call_webapp("pushCandle", {"candles": candles})

        return jsonify({
            "ok": True,
            "symbol": symbol,
            "candles_pushed": len(candles),
            "times": [c["time"] for c in candles]
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

# ------------------------------------------------------------
# ROOT
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def root():
    return "Historical Candle Engine LIVE (09:15–09:30)", 200

# ------------------------------------------------------------
# RUN
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
