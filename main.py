# ============================================================
# RajanTradeAutomation – FYERS WS Debug Stable (Render Ready)
# ============================================================

import os
import threading
import time
import traceback
from flask import Flask

# -------------------------
# ENV CHECK
# -------------------------
print("🚀 main.py STARTED")

FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

print("🔍 ENV CHECK")
print("FYERS_CLIENT_ID =", FYERS_CLIENT_ID)
print("FYERS_ACCESS_TOKEN prefix =", FYERS_ACCESS_TOKEN[:20] if FYERS_ACCESS_TOKEN else "❌ MISSING")

if not FYERS_CLIENT_ID or not FYERS_ACCESS_TOKEN:
    raise Exception("❌ FYERS ENV variables missing")

# -------------------------
# FYERS WS IMPORT
# -------------------------
print("📦 Importing fyers_apiv3.FyersWebsocket.data_ws")

from fyers_apiv3.FyersWebsocket import data_ws

print("✅ data_ws IMPORT SUCCESS")

# -------------------------
# FLASK (Render needs port bind)
# -------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "RajanTradeAutomation LIVE"

@app.route("/ping")
def ping():
    return "PONG"

# -------------------------
# FYERS CALLBACKS
# -------------------------
def on_message(message):
    print("📩 WS MESSAGE:", message)

def on_error(error):
    print("❌ WS ERROR:", error)

def on_close(message):
    print("🔌 WS CLOSED:", message)

# -------------------------
# WS THREAD
# -------------------------
def start_ws():
    try:
        print("🧠 Creating FyersDataSocket")

        ws = data_ws.FyersDataSocket(
            access_token=FYERS_ACCESS_TOKEN,
            log_path="",
            litemode=False,
            write_to_file=False,
            reconnect=True,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )

        print("✅ FyersDataSocket CREATED")

        symbols = [
            "NSE:SBIN-EQ",
            "NSE:RELIANCE-EQ",
            "NSE:VEDL-EQ",
            "NSE:AXISBANK-EQ",
            "NSE:KOTAKBANK-EQ"
        ]

        print("📡 Subscribing symbols:", symbols)
        ws.subscribe(symbols=symbols, data_type="SymbolUpdate")

        print("🔁 keep_running() START (blocking)")
        ws.keep_running()

        print("⚠️ keep_running EXITED (should NOT happen)")

    except Exception as e:
        print("🔥 WS THREAD CRASHED")
        traceback.print_exc()

# -------------------------
# START WS THREAD
# -------------------------
ws_thread = threading.Thread(target=start_ws)
ws_thread.start()
print("🧵 WS THREAD STARTED")

# -------------------------
# START FLASK
# -------------------------
port = int(os.environ.get("PORT", 10000))
print(f"🌐 Starting Flask on port {port}")
app.run(host="0.0.0.0", port=port)
