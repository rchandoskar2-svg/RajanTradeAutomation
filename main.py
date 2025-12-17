# ============================================================
# RajanTradeAutomation – MAIN
# Historical Candle Test (09:15–09:30, 5m)
# ============================================================

from flask import Flask, jsonify
import requests
import os
from datetime import datetime
import pytz
import traceback

app = Flask(__name__)

# ------------------------------------------------------------
# ENV
# ------------------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

FYERS_HIST_URL = "https://api.fyers.in/data-rest/v2/history"
IST = pytz.timezone("Asia/Kolkata")

# ------------------------------------------------------------
# SAFE WebApp Caller
# ------------------------------------------------------------
def call_webapp(action, payload):
    try:
        res = requests.post(
            WEBAPP_URL,
            json={"action": action, "payload": payload},
            timeout=20
        )
        try:
            return res.json()
        except Exception:
            return {
                "ok": False,
                "error": "WebApp returned non-JSON",
                "status": res.status_code,
                "raw": res.text[:300]
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ------------------------------------------------------------
# FYERS Historical Fetch (CRASH SAFE)
# ------------------------------------------------------------
def fetch_915_candles(symbol):
    try:
        today = datetime.now(IST).date()

        params = {
            "symbol": symbol,
            "resolution": "5",
            "date_format": "1",
            "range_from": today.strftime("%Y-%m-%d"),
            "range_to": today.strftime("%Y-%m-%d"),
            "cont_flag": "1"
        }

        headers = {
            "Authorization": f"Bearer {FYERS_ACCESS_TOKEN}"
        }

        r = requests.get(FYERS_HIST_URL, params=params, headers=headers, timeout=20)

        try:
            data = r.json()
        except Exception:
            return {"error": "FYERS returned non-JSON", "raw": r.text[:300]}

        if data.get("s") != "ok":
            return {"error": "FYERS error", "response": data}

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

        return {"candles": candles}

    except Exception:
        return {
            "error": "Python exception",
            "trace": traceback.format_exc()
        }

# ------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------
@app.route("/")
def root():
    return "Historical Candle Engine LIVE", 200


@app.route("/test/historical-915")
def test_historical():
    result = fetch_915_candles("NSE:SBIN-EQ")

    if "error" in result:
        return jsonify({"ok": False, **result})

    candles = result["candles"]

    if not candles:
        return jsonify({"ok": False, "error": "No candles found"})

    push = call_webapp("pushCandle", {"candles": candles})

    return jsonify({
        "ok": True,
        "candles_count": len(candles),
        "push_result": push
    })


# ------------------------------------------------------------
# START
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
