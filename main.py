# ============================================================
# RajanTradeAutomation – main.py
# LIVE FYERS WS + 5-Minute Candle Engine + Watchdog
# BASE LOCKED: Flask + Callback + WS thread MUST NOT CHANGE
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
# GLOBAL WS STATE (WATCHDOG)
# ------------------------------------------------------------
last_tick_time = 0

# ------------------------------------------------------------
# 5-MINUTE CANDLE ENGINE (IN-MEMORY)
# ------------------------------------------------------------
CANDLE_INTERVAL = 300  # 5 minutes

# candle_state[symbol] = {
#   bucket, open, high, low, close, volume, start_time
# }
candle_state = {}

def get_bucket(ts):
    return ts - (ts % CANDLE_INTERVAL)

def finalize_candle(symbol, candle):
    print(
        f"🕯️ 5m CANDLE CLOSED | {symbol} | "
        f"O:{candle['open']} H:{candle['high']} "
        f"L:{candle['low']} C:{candle['close']} "
        f"V:{candle['volume']} | "
        f"@ {datetime.fromtimestamp(candle['start_time']).strftime('%H:%M')}"
    )

# ------------------------------------------------------------
# WebSocket Callbacks
# ------------------------------------------------------------
def on_message(message):
    global last_tick_time
    try:
        if message.get("type") != "sf":
            return

        last_tick_time = time.time()

        symbol = message["symbol"]
        ltp = float(message["ltp"])
        volume = int(message.get("last_traded_qty", 0))
        ts = int(message.get("last_traded_time", time.time()))

        bucket = get_bucket(ts)

        if symbol not in candle_state:
            candle_state[symbol] = {
                "bucket": bucket,
                "open": ltp,
                "high": ltp,
                "low": ltp,
                "close": ltp,
                "volume": volume,
                "start_time": bucket
            }
            return

        candle = candle_state[symbol]

        # SAME BUCKET
        if bucket == candle["bucket"]:
            candle["high"] = max(candle["high"], ltp)
            candle["low"] = min(candle["low"], ltp)
            candle["close"] = ltp
            candle["volume"] += volume

        # NEW BUCKET → CLOSE OLD
        else:
            finalize_candle(symbol, candle)

            candle_state[symbol] = {
                "bucket": bucket,
                "open": ltp,
                "high": ltp,
                "low": ltp,
                "close": ltp,
                "volume": volume,
                "start_time": bucket
            }

    except Exception as e:
        print("🔥 on_message ERROR:", e)

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
# WS WATCHDOG (AUTO-REVIVE FOR RENDER)
# ------------------------------------------------------------
def ws_watchdog():
    global last_tick_time
    while True:
        time.sleep(15)
        if last_tick_time == 0:
            continue

        if time.time() - last_tick_time > 20:
            print("⚠️ WS STALE – RECONNECTING")
            try:
                fyers_ws.connect()
            except Exception as e:
                print("🔥 WS RECONNECT FAILED:", e)

# ------------------------------------------------------------
# Launch Threads
# ------------------------------------------------------------
ws_thread = threading.Thread(target=start_ws, daemon=True)
ws_thread.start()

watchdog_thread = threading.Thread(target=ws_watchdog, daemon=True)
watchdog_thread.start()

# ------------------------------------------------------------
# Start Flask (MAIN THREAD)
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Starting Flask on port {port}")
    app.run(host="0.0.0.0", port=port)
