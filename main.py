# ============================================================
# RajanTradeAutomation – MAIN (Historical Candle Test ONLY)
# Purpose: Fetch 5m candles (09:15–09:30) & push to WebApp
# ============================================================

from flask import Flask, jsonify
import requests
import os
import time
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)

# ------------------------------------------------------------
# ENVIRONMENT VARIABLES (Render)
# ------------------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

FYERS_HIST_URL = "https://api.fyers.in/data-rest/v2/history"

IST = pytz.timezone("Asia/Kolkata")

# ------------------------------------------------------------
# SAFE WebApp Caller (NO JSON CRASH)
# ------------------------------------------------------------
def call_webapp(action, payload):
    if not WEBAPP_URL:
        return {"ok": False, "error": "WEBAPP_URL missing"}

    body = {"action": action, "payload": payload}

    try:
        res = requests.post(WEBAPP_URL, json=body, timeout=20)

        try:
            return res.json()
        except Exception:
            return {
                "ok": False,
                "error": "Invalid JSON from WebApp",
                "status": res.status_code,
                "raw": res.text[:300]
            }

    except Exception as e:
        return {"ok": False, "error": str(e)}

# ------------------------------------------------------------
# FYERS Historical Candle Fetch
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

    r = requests.get(FYERS_HIST_URL, params=params, headers=headers, timeout=20)
    data = r.json()

    if data.get("s") != "ok":
        return []

    candles = []
    idx = 1

    for c in data.get("candles", []):
        ts = datetime.fromtimestamp(c[0], IST)
        if ts.strftime("%H:%M") not in ("09:15", "09:20", "09:25"):
            continue

        candles.append({
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

    return candles

# ------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def root():
    return "RajanTradeAutomation – Historical Candle Engine LIVE", 200

@app.route("/test/historical-915", methods=["GET"])
def test_historical():
    symbol = "NSE:SBIN-EQ"

    candles = fetch_915_candles(symbol)

    if not candles:
        return jsonify({"ok": False, "error": "No candles fetched"})

    result = call_webapp("pushCandle", {"candles": candles})

    return jsonify({
        "ok": True,
        "candles_count": len(candles),
        "webapp_response": result
    })

# ------------------------------------------------------------
# FLASK START
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
