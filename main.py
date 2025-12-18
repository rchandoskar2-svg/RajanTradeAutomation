# ============================================================
# RajanTradeAutomation – FYERS LIVE DATA DEBUG ENGINE
# Purpose: Confirm WS connection + ticks on Render
# ============================================================

import os
import time
import threading
from flask import Flask

# -----------------------------
# ENV CHECK
# -----------------------------
print("🚀 main.py STARTED")

FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
if not FYERS_ACCESS_TOKEN:
    print("❌ FYERS_ACCESS_TOKEN MISSING")
else:
    print("✅ FYERS_ACCESS_TOKEN prefix:", FYERS_ACCESS_TOKEN[:20])

# -----------------------------
# FYERS WS IMPORT
# -----------------------------
print("📦 Importing fyers_apiv3.FyersWebsocket.data_ws")
from fyers_apiv3.FyersWebsocket import data_ws
print("✅ data_ws import SUCCESS")

# -----------------------------
# FLASK (only for ping / keep alive)
# -----------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "RajanTradeAutomation LIVE WS DEBUG", 200

@app.route("/ping")
def ping():
    return "PONG", 200

# -----------------------------
# SYMBOLS (FIXED – SMALL SET)
# -----------------------------
SYMBOLS = [
    "NSE:SBIN-EQ",
    "NSE:RELIANCE-EQ",
    "NSE:VEDL-EQ",
    "NSE:AXISBANK-EQ",
    "NSE:KOTAKBANK-EQ",
]

# -----------------------------
# WS CALLBACKS
# -----------------------------
def on_open():
    print("🟢 WS CONNECTED")

def on_close(msg):
    print("🔴 WS CLOSED:", msg)

def on_error(err):
    print("❌ WS ERROR:", err)

def on_message(msg):
    print("📩 TICK:", msg)

# -----------------------------
# WS THREAD
# -----------------------------
def start_ws():
    print("🧵 WS THREAD STARTED")

    ws = data_ws.FyersDataSocket(
        access_token=FYERS_ACCESS_TOKEN,
        log_path="",
        litemode=False,
        write_to_file=False,
        reconnect=True,
        on_connect=on_open,
        on_close=on_close,
        on_error=on_error,
        on_message=on_message,
    )

    print("📡 Subscribing symbols:", SYMBOLS)
    ws.subscribe(symbols=SYMBOLS, data_type="SymbolUpdate")

    print("🔁 Calling keep_running()")
    ws.keep_running()

    # SAFETY BLOCK (Render needs this)
    while True:
        time.sleep(10)

# -----------------------------
# START WS THREAD (NON-DAEMON)
# -----------------------------
t = threading.Thread(target=start_ws, daemon=False)
t.start()

# -----------------------------
# START FLASK
# -----------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    print("🌐 Starting Flask on port", port)
    app.run(host="0.0.0.0", port=port)
