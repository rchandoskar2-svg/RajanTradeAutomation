# ============================================================
# RajanTradeAutomation – Main Backend
# ONLY Historical Candle Test (9:15–9:30)
# ============================================================

from flask import Flask, jsonify
import requests
import os
from datetime import datetime, time as dtime
from dateutil import tz

app = Flask(__name__)

# ------------------------------------------------------------
# ENV
# ------------------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

FYERS_HISTORY_URL = "https://api.fyers.in/data-rest/v2/history"

IST = tz.gettz("Asia/Kolkata")

# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------
def call_webapp(action, payload):
    body = {"action": action, "payload": payload}
    res = requests.post(WEBAPP_URL, json=body, timeout=20)

    if res.status_code != 200:
        raise Exception(res.text)

    return res.json()


def fetch_historical_915(symbol):
    today = datetime.now(IST).date()

    start_dt = datetime.combine(today, dtime(9, 15), IST)
    end_dt   = datetime.combine(today, dtime(9, 30), IST)

    payload = {
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

    r = requests.get(FYERS_HISTORY_URL, params=payload, headers=headers)
    data = r.json()

    if data.get("s") != "ok":
        raise Exception(data)

    candles = []
    for idx, c in enumerate(data["candles"]):
        ts, o, h, l, cl, v = c
        candle_time = datetime.fromtimestamp(ts, IST)

        if candle_time.time() >= dtime(9,15) and candle_time.time() < dtime(9,30):
            candles.append({
                "symbol": symbol,
                "time": candle_time.isoformat(),
                "timeframe": "5m",
                "open": o,
                "high": h,
                "low": l,
                "close": cl,
                "volume": v,
                "candle_index": idx + 1,
                "lowest_volume_so_far": v,
                "is_signal": False,
                "direction": ""
            })

    return candles


# ------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def root():
    return "RajanTradeAutomation – Historical Test Ready", 200


@app.route("/test/historical-915", methods=["GET"])
def test_historical_915():
    try:
        symbol = "NSE:SBIN-EQ"

        candles = fetch_historical_915(symbol)

        if not candles:
            return jsonify({"ok": False, "error": "No candles found"})

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
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
