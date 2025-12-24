# ============================================================
# RajanPushpaRaj – main.py (FINAL LOCKED VERSION)
# Render-safe | FYERS WS | Redirect URI | 5m Candle (Cum Vol)
# ============================================================

import os
import time
import threading
from flask import Flask, jsonify, request

print("🚀 main.py STARTED")

# ------------------------------------------------------------
# ENV CHECK
# ------------------------------------------------------------
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

print("🔍 ENV CHECK")
print("FYERS_CLIENT_ID =", FYERS_CLIENT_ID)
print(
    "FYERS_ACCESS_TOKEN prefix =",
    FYERS_ACCESS_TOKEN[:20] if FYERS_ACCESS_TOKEN else "❌ MISSING"
)

if not FYERS_CLIENT_ID or not FYERS_ACCESS_TOKEN:
    raise Exception("❌ FYERS ENV variables missing")

# ------------------------------------------------------------
# Flask App
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({
        "status": "ok",
        "service": "RajanPushpaRaj"
    })

# ------------------------------------------------------------
# FYERS REDIRECT URI (FINAL)
# ------------------------------------------------------------
@app.route("/fyers-redirect", methods=["GET"])
def fyers_redirect():
    auth_code = request.args.get("auth_code") or request.args.get("code")
    state = request.args.get("state")

    print("🔑 FYERS REDIRECT HIT")
    print("AUTH CODE =", auth_code)
    print("STATE =", state)

    if not auth_code:
        return jsonify({"error": "auth_code missing"}), 400

    return jsonify({
        "status": "redirect_received",
        "auth_code": auth_code,
        "state": state
    })

# ------------------------------------------------------------
# Import FYERS WebSocket
# ------------------------------------------------------------
from fyers_apiv3.FyersWebsocket import data_ws

# ------------------------------------------------------------
# 5-MIN CANDLE ENGINE
# ------------------------------------------------------------
CANDLE_INTERVAL = 300

candles = {}
last_candle_vol = {}

def get_candle_start(ts):
    return ts - (ts % CANDLE_INTERVAL)

def close_candle(symbol, c):
    prev_vol = last_candle_vol.get(symbol, c["cum_vol"])
    candle_volume = c["cum_vol"] - prev_vol
    last_candle_vol[symbol] = c["cum_vol"]

    print(
        f"\n🟩 5m CANDLE {symbol}"
        f"\nO:{c['open']} H:{c['high']} L:{c['low']} "
        f"C:{c['close']} | Vol:{candle_volume}"
    )

def update_candle_from_tick(tick):
    if not isinstance(tick, dict):
        return

    symbol = tick.get("symbol")
    ltp = tick.get("ltp")
    vol = tick.get("vol_traded_today")
    ts = tick.get("exch_feed_time")

    if not symbol or ltp is None or vol is None or ts is None:
        return

    candle_start = get_candle_start(ts)
    c = candles.get(symbol)

    if c is None or c["start"] != candle_start:
        if c:
            close_candle(symbol, c)

        candles[symbol] = {
            "start": candle_start,
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
# WebSocket Callbacks
# ------------------------------------------------------------
def on_message(message):
    if isinstance(message, list):
        for tick in message:
            update_candle_from_tick(tick)
    elif isinstance(message, dict):
        update_candle_from_tick(message)

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

# ------------------------------------------------------------
# Start WebSocket
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
    app.run(host="0.0.0.0", port=port)
