# ============================================================
# RajanTradeAutomation – main.py
# Render Stable WS + Local-Proven 5m Candle
# + Volume Verification Debug
# + Test /status Route
# ============================================================

import os
import time
import threading
from datetime import datetime
from flask import Flask, jsonify, request

# ------------------------------------------------------------
# START LOG
# ------------------------------------------------------------
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
# Flask App (Render keep-alive + FYERS redirect)
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({
        "status": "ok",
        "service": "RajanTradeAutomation",
        "time": datetime.now().strftime("%H:%M:%S")
    })

# 🔎 TEST ROUTE (browser friendly)
@app.route("/status")
def status():
    return jsonify({
        "active_symbols": list(candles.keys()),
        "current_candles": {
            s: {
                "start": c["start"],
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "cum_vol": c["cum_vol"]
            }
            for s, c in candles.items()
        }
    })

# ✅ REQUIRED FOR FYERS AUTH FLOW
@app.route("/callback")
def fyers_callback():
    auth_code = request.args.get("auth_code")
    print("🔑 FYERS CALLBACK HIT | AUTH CODE =", auth_code)

    if not auth_code:
        return jsonify({"error": "auth_code missing"}), 400

    return jsonify({
        "status": "callback_received",
        "auth_code": auth_code
    })

# ------------------------------------------------------------
# FYERS WebSocket
# ------------------------------------------------------------
print("📦 Importing fyers_apiv3 WebSocket")
from fyers_apiv3.FyersWebsocket import data_ws
print("✅ data_ws IMPORT SUCCESS")

# ------------------------------------------------------------
# 5-MIN CANDLE ENGINE (LOCAL-PROVEN + DEBUG)
# ------------------------------------------------------------
CANDLE_INTERVAL = 300  # 5 minutes

candles = {}          # symbol -> current candle
last_candle_vol = {}  # symbol -> last candle cumulative volume

def get_candle_start(ts):
    return ts - (ts % CANDLE_INTERVAL)

def close_candle(symbol, c):
    prev_vol = last_candle_vol.get(symbol, c["cum_vol"])
    candle_volume = c["cum_vol"] - prev_vol

    # 🔎 DEBUG (VERIFICATION)
    print(
        f"🔎 VOL DEBUG | {symbol} | "
        f"prev_cum={prev_vol} curr_cum={c['cum_vol']} diff={candle_volume}"
    )

    last_candle_vol[symbol] = c["cum_vol"]

    # 🟩 FINAL CANDLE PRINT
    print(
        f"\n🟩 5m CANDLE {symbol}"
        f"\nTime : {time.strftime('%H:%M:%S', time.localtime(c['start']))}"
        f"\nO:{c['open']} H:{c['high']} L:{c['low']} "
        f"C:{c['close']} V:{candle_volume}"
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

    candle_start = get_candle_start(ts)
    c = candles.get(symbol)

    # NEW CANDLE
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

    # UPDATE RUNNING CANDLE
    c["high"] = max(c["high"], ltp)
    c["low"] = min(c["low"], ltp)
    c["close"] = ltp
    c["cum_vol"] = vol

# ------------------------------------------------------------
# WebSocket Callbacks
# ------------------------------------------------------------
def on_message(message):
    # 🔒 Existing behaviour untouched
    print("📩 WS MESSAGE:", message)

    try:
        update_candle_from_tick(message)
    except Exception as e:
        print("🔥 Candle logic error:", e)

def on_error(message):
    print("❌ WS ERROR:", message)

def on_close(message):
    print("🔌 WS CLOSED:", message)

def on_connect():
    print("🔗 WS CONNECTED")

    symbols = [
        "NSE:SBIN-EQ",
        "NSE:RELIANCE-EQ",
        "NSE:VEDL-EQ",
        "NSE:AXISBANK-EQ",
        "NSE:KOTAKBANK-EQ"
    ]

    print("📡 Subscribing symbols:", symbols)

    fyers_ws.subscribe(
        symbols=symbols,
        data_type="SymbolUpdate"
    )

# ------------------------------------------------------------
# Start WebSocket (NON-BLOCKING)
# ------------------------------------------------------------
def start_ws():
    try:
        print("🧵 WS THREAD STARTED")

        global fyers_ws
        fyers_ws = data_ws.FyersDataSocket(
            access_token=FYERS_ACCESS_TOKEN,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_connect=on_connect,
            reconnect=True
        )

        print("✅ FyersDataSocket CREATED")
        fyers_ws.connect()
        print("📶 WS CONNECT CALLED")

    except Exception as e:
        print("🔥 WS THREAD CRASHED:", e)

# ------------------------------------------------------------
# Launch WS in daemon thread
# ------------------------------------------------------------
ws_thread = threading.Thread(target=start_ws, daemon=True)
ws_thread.start()

# ------------------------------------------------------------
# Start Flask (MAIN THREAD)
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Starting Flask on port {port}")
    app.run(host="0.0.0.0", port=port)
