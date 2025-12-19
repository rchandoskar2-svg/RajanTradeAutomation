# ============================================================
# RajanTradeAutomation – main.py
# FYERS LIVE WS + 5m Candle + SAFE Watchdog
# ============================================================

import os
import time
import threading
from datetime import datetime
from flask import Flask, jsonify, request

# ------------------------------------------------------------
# START
# ------------------------------------------------------------
print("🚀 main.py STARTED")

FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

if not FYERS_CLIENT_ID or not FYERS_ACCESS_TOKEN:
    raise Exception("❌ FYERS ENV missing")

# ------------------------------------------------------------
# Flask (Render keep-alive + FYERS redirect)
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({"status": "ok", "time": datetime.now().strftime("%H:%M:%S")})

@app.route("/callback")
def fyers_callback():
    return jsonify({"auth_code": request.args.get("auth_code")})

# ------------------------------------------------------------
# FYERS WS
# ------------------------------------------------------------
from fyers_apiv3.FyersWebsocket import data_ws

fyers_ws = None
last_tick_time = 0
ws_lock = threading.Lock()

# ------------------------------------------------------------
# 5m Candle Engine
# ------------------------------------------------------------
CANDLE_INTERVAL = 300
candle_state = {}

def get_bucket(ts):
    return ts - (ts % CANDLE_INTERVAL)

def finalize_candle(symbol, c):
    print(
        f"🕯️ 5m CANDLE | {symbol} | "
        f"O:{c['open']} H:{c['high']} L:{c['low']} "
        f"C:{c['close']} V:{c['volume']} | "
        f"{datetime.fromtimestamp(c['start']).strftime('%H:%M')}"
    )

# ------------------------------------------------------------
# WS Callbacks
# ------------------------------------------------------------
def on_message(msg):
    global last_tick_time
    if msg.get("type") != "sf":
        return

    last_tick_time = time.time()

    symbol = msg["symbol"]
    ltp = float(msg["ltp"])
    qty = int(msg.get("last_traded_qty", 0))
    ts = int(msg.get("last_traded_time", time.time()))

    bucket = get_bucket(ts)

    if symbol not in candle_state:
        candle_state[symbol] = {
            "bucket": bucket,
            "open": ltp,
            "high": ltp,
            "low": ltp,
            "close": ltp,
            "volume": qty,
            "start": bucket
        }
        return

    c = candle_state[symbol]

    if bucket == c["bucket"]:
        c["high"] = max(c["high"], ltp)
        c["low"] = min(c["low"], ltp)
        c["close"] = ltp
        c["volume"] += qty
    else:
        finalize_candle(symbol, c)
        candle_state[symbol] = {
            "bucket": bucket,
            "open": ltp,
            "high": ltp,
            "low": ltp,
            "close": ltp,
            "volume": qty,
            "start": bucket
        }

def on_error(msg):
    print("❌ WS ERROR:", msg)

def on_close(msg):
    print("🔌 WS CLOSED:", msg)

def on_connect():
    print("🔗 WS CONNECTED")
    fyers_ws.subscribe(
        symbols=[
            "NSE:SBIN-EQ",
            "NSE:RELIANCE-EQ",
            "NSE:VEDL-EQ",
            "NSE:AXISBANK-EQ",
            "NSE:KOTAKBANK-EQ"
        ],
        data_type="SymbolUpdate"
    )

# ------------------------------------------------------------
# WS START (CREATE SOCKET)
# ------------------------------------------------------------
def create_ws():
    global fyers_ws
    print("🧵 Creating NEW WS socket")
    fyers_ws = data_ws.FyersDataSocket(
        access_token=FYERS_ACCESS_TOKEN,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_connect=on_connect,
        reconnect=True
    )
    fyers_ws.connect()

# ------------------------------------------------------------
# WATCHDOG (SAFE)
# ------------------------------------------------------------
def ws_watchdog():
    while True:
        time.sleep(15)
        if last_tick_time == 0:
            continue

        if time.time() - last_tick_time > 20:
            print("⚠️ WS STALE → RECREATING SOCKET")
            with ws_lock:
                create_ws()

# ------------------------------------------------------------
# THREADS
# ------------------------------------------------------------
threading.Thread(target=create_ws, daemon=True).start()
threading.Thread(target=ws_watchdog, daemon=True).start()

# ------------------------------------------------------------
# Flask main
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
