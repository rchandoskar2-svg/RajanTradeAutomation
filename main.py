# ============================================================
# RajanTradeAutomation – Main Backend (Render / Flask)
# Version: 6.2 (Historical FIX + Candle Push FIX + Logging FIX)
# ============================================================

from flask import Flask, request, jsonify
import requests
import os
import time
import traceback

app = Flask(__name__)

# ------------------------------------------------------------
# GOOGLE SHEETS WEBAPP URL
# ------------------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL")

if not WEBAPP_URL:
    print("ERROR: WEBAPP_URL not found in environment!")

# ------------------------------------------------------------
# SAFE POST FUNCTION
# ------------------------------------------------------------
def safe_post(payload):
    try:
        r = requests.post(WEBAPP_URL, json=payload, timeout=10)
        return r.text
    except Exception as e:
        print("POST ERROR:", e)
        return str(e)

# ------------------------------------------------------------
# HEALTH CHECK
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "ok", "message": "RajanTradeAutomation Backend Running"})


# ============================================================
#  HISTORICAL CANDLE FILL (09:15 to 09:30)
# ============================================================
@app.route("/fillHistorical", methods=["POST"])
def fillHistorical():
    try:
        data = request.json
        symbol = data.get("symbol")
        candles = data.get("candles", [])

        if not symbol or not candles:
            return jsonify({"error": "Missing symbol or candles"}), 400

        # Push each candle to Google Sheets
        for c in candles:
            payload = {
                "action": "pushCandle",
                "symbol": symbol,
                "time": c["time"],
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": c["volume"]
            }
            safe_post(payload)

        # Log
        safe_post({
            "action": "log",
            "message": f"Historical candles filled for {symbol}"
        })

        return jsonify({"ok": True, "message": "Historical candles filled"})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)})


# ============================================================
#  LIVE CANDLE PUSH (Every 1 minute)
# ============================================================
@app.route("/pushLiveCandle", methods=["POST"])
def pushLiveCandle():
    try:
        data = request.json
        symbol = data.get("symbol")
        candle = data.get("candle")

        if not symbol or not candle:
            return jsonify({"error": "Missing symbol or candle"}), 400

        payload = {
            "action": "pushCandle",
            "symbol": symbol,
            "time": candle["time"],
            "open": candle["open"],
            "high": candle["high"],
            "low": candle["low"],
            "close": candle["close"],
            "volume": candle["volume"]
        }

        safe_post(payload)

        # Logs update properly
        safe_post({
            "action": "log",
            "message": f"Live candle pushed: {symbol}"
        })

        return jsonify({"ok": True, "message": "Live candle pushed"})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)})


# ============================================================
#  PRICE UPDATE (WebSocket → every tick)
# ============================================================
@app.route("/priceUpdate", methods=["POST"])
def priceUpdate():
    try:
        data = request.json
        symbol = data.get("symbol")
        price = data.get("price")

        if not symbol:
            return jsonify({"error": "Missing symbol"}), 400

        safe_post({
            "action": "pushPrice",
            "symbol": symbol,
            "price": price
        })

        return jsonify({"ok": True})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)})


# ============================================================
#  SIGNAL PUSH (Buy / Sell)
# ============================================================
@app.route("/signal", methods=["POST"])
def signal():
    try:
        data = request.json

        safe_post({
            "action": "pushSignal",
            "signal": data
        })

        safe_post({
            "action": "log",
            "message": f"Signal pushed: {data}"
        })

        return jsonify({"ok": True})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)})


# ============================================================
#  ENTRY / EXIT HANDLERS
# ============================================================
@app.route("/entry", methods=["POST"])
def entry():
    try:
        data = request.json

        safe_post({
            "action": "pushTradeEntry",
            "trade": data
        })

        safe_post({
            "action": "log",
            "message": f"Entry: {data}"
        })

        return jsonify({"ok": True})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)})


@app.route("/exit", methods=["POST"])
def exit():
    try:
        data = request.json

        safe_post({
            "action": "pushTradeExit",
            "trade": data
        })

        safe_post({
            "action": "log",
            "message": f"Exit: {data}"
        })

        return jsonify({"ok": True})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)})


# ============================================================
#  LIVESTATE UPDATE
# ============================================================
@app.route("/liveState", methods=["POST"])
def liveState():
    try:
        data = request.json

        safe_post({
            "action": "pushLiveState",
            "state": data
        })

        return jsonify({"ok": True})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)})


# ============================================================
#  MANUAL LOG
# ============================================================
@app.route("/log", methods=["POST"])
def log():
    try:
        msg = request.json.get("message", "")
        safe_post({"action": "log", "message": msg})
        return jsonify({"ok": True})
    except:
        return jsonify({"error": "log failed"})


# ============================================================
# RUN
# ============================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
