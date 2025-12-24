# ============================================================
# RajanTradeAutomation – main.py (Render Stable WS Version)
# SILENT TICK MODE (NO SKIP)
# FIXED: setuptools<81, FYERS WS, Render-safe threading
# + FYERS REDIRECT URI
# + PING ROUTE
# + LOCAL-PROVEN 5-MIN CANDLE BUILD
# ============================================================

import os
import time
import threading
from flask import Flask, jsonify, request

# ------------------------------------------------------------
# Startup Log
# ------------------------------------------------------------
print("🚀 main.py STARTED")

# ------------------------------------------------------------
# ENV CHECK
# ------------------------------------------------------------
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

print("🔍 ENV CHECK")
print("FYERS_CLIENT_ID =", FYERS_CLIENT_ID)
print("FYERS_ACCESS_TOKEN prefix =", FYERS_ACCESS_TOKEN[:15] if FYERS_ACCESS_TOKEN else "❌ MISSING")

if not FYERS_CLIENT_ID or not FYERS_ACCESS_TOKEN:
    raise Exception("❌ FYERS ENV variables missing")

# ------------------------------------------------------------
# Flask App
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "RajanTradeAutomation"})

@app.route("/ping")
def ping():
    return "pong", 200

# ------------------------------------------------------------
# FYERS REDIRECT URI
# ------------------------------------------------------------
@app.route("/fyers-redirect", methods=["GET"])
def fyers_redirect():
    auth_code = request.args.get("auth_code") or request.args.get("code")
    state = request.args.get("state")

    print("🔑 FYERS REDIRECT HIT")
    print("AUTH CODE =", auth_code)

    if not auth_code:
        return jsonify({"error": "auth_code missing"}), 400

    return jsonify({
        "status": "redirect_received",
        "auth_code": auth_code,
        "state": state
    })

# ------------------------------------------------------------
# FYERS WebSocket
# ------------------------------------------------------------
from fyers_apiv3.FyersWebsocket import data_ws
print("✅ data_ws IMPORTED")

# ------------------------------------------------------------
# 5-MIN CANDLE ENGINE (STRICT)
# ------------------------------------------------------------
CANDLE_INTERVAL = 300

candles = {}
last_candle_vol = {}

def get_candle_start(ts):
    return ts - (ts % CANDLE_INTERVAL)

def close_candle(symbol, c):
    prev_vol = last_candle_vol.get(symbol, c["cum_vol"])
    candle_vol = c["cum_vol"] - prev_vol
    last_candle_vol[symbol] = c["cum_vol"]

    print(
        f"\n🟩 5m CANDLE {symbol}"
        f"\nTime : {time.strftime('%H:%M:%S', time.localtime(c['start']))}"
        f"\nO:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']} V:{candle_vol}"
        f"\n---------------------------"
    )

def update_candle_from_tick(msg):
    if not isinstance(msg, dict):
        return

    symbol = msg.get("symbol")
    ltp = msg.get("ltp")
    vol = msg.get("vol_traded_today")
    ts = msg.get("exch_feed_time")

    if not symbol or ltp is None or vol is None or ts is None:
        return

    start = get_candle_start(ts)
    c = candles.get(symbol)

    if c is None or c["start"] != start:
        if c:
            close_candle(symbol, c)

        candles[symbol] = {
            "start": start,
            "open": ltp,
            "high": ltp,
            "low": ltp,
            "close": ltp,
            "cum_vol": vol
        }
        return

    c["high"] = max(c["high"], ltp)
    c["low"] = min(c["low"], ltp)
    c["close"] = ltp
    c["cum_vol"] = vol

# ------------------------------------------------------------
# WebSocket Callbacks (NO TICK PRINT, NO SKIP)
# ------------------------------------------------------------
def on_message(message):
    try:
        update_candle_from_tick(message)
    except Exception as e:
        print("🔥 Candle logic error:", e)

def on_error(message):
    print("❌ WS ERROR:", message)

def on_close(message):
    print("🔌 WS CLOSED")

def on_connect():
    print("🔗 WS CONNECTED")

    symbols = [
        "NSE:SBIN-EQ",
        "NSE:RELIANCE-EQ",
        "NSE:VEDL-EQ",
        "NSE:AXISBANK-EQ",
        "NSE:KOTAKBANK-EQ"
    ]

    fyers_ws.subscribe(symbols=symbols, data_type="SymbolUpdate")
    print("📡 SUBSCRIBED:", symbols)

# ------------------------------------------------------------
# Start WS Thread
# ------------------------------------------------------------
def start_ws():
    global fyers_ws
    fyers_ws = data_ws.FyersDataSocket(
        access_token=FYERS_ACCESS_TOKEN,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_connect=on_connect,
        reconnect=True
    )
    fyers_ws.connect()

threading.Thread(target=start_ws, daemon=True).start()

# ------------------------------------------------------------
# Start Flask
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Flask starting on port {port}")
    app.run(host="0.0.0.0", port=port)
