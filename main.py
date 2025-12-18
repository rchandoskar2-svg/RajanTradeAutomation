# ============================================================
# RajanTradeAutomation – FYERS WS DEBUG MODE
# PURPOSE: ONLY verify WS connection & ticks on Render
# ============================================================

import os
import time
import threading
from flask import Flask

print("🚀 main.py STARTED")

# ------------------------------------------------------------
# ENV CHECK
# ------------------------------------------------------------
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

print("🔎 ENV CHECK")
print("FYERS_CLIENT_ID:", FYERS_CLIENT_ID)
print("FYERS_ACCESS_TOKEN prefix:", FYERS_ACCESS_TOKEN[:15])

if not FYERS_CLIENT_ID or not FYERS_ACCESS_TOKEN:
    print("❌ FYERS ENV MISSING – EXITING")
    exit(1)

# ------------------------------------------------------------
# IMPORT FYERS WS
# ------------------------------------------------------------
print("📦 Importing fyers_apiv3.FyersWebsocket.data_ws")
from fyers_apiv3.FyersWebsocket import data_ws
print("✅ data_ws IMPORT SUCCESS")

# ------------------------------------------------------------
# FLASK (ONLY FOR RENDER HEALTH)
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "RajanTradeAutomation WS DEBUG LIVE", 200

@app.route("/ping")
def ping():
    return "PONG", 200

# ------------------------------------------------------------
# WS CALLBACKS (VERY VERBOSE)
# ------------------------------------------------------------
def onopen():
    print("🟢 WS CONNECTED (onopen called)")

def onmessage(message):
    print("📩 WS MESSAGE RECEIVED")
    print(message)

def onerror(error):
    print("🔴 WS ERROR")
    print(error)

def onclose(reason):
    print("⚫ WS CLOSED")
    print(reason)

# ------------------------------------------------------------
# WS THREAD
# ------------------------------------------------------------
def start_ws():
    try:
        print("🔧 Creating FyersDataSocket()")

        access_token = f"{FYERS_CLIENT_ID}:{FYERS_ACCESS_TOKEN}"

        ws = data_ws.FyersDataSocket(
            access_token=access_token,
            log_path="",
            litemode=False,
            write_to_file=False,
            reconnect=True,
            on_connect=onopen,
            on_close=onclose,
            on_error=onerror,
            on_message=onmessage
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

        ws.subscribe(
            symbols=symbols,
            data_type="SymbolUpdate"
        )

        print("▶ Calling keep_running() (BLOCKING CALL)")
        ws.keep_running()

        print("❌ keep_running EXITED (should NOT happen)")

    except Exception as e:
        print("🔥 WS THREAD EXCEPTION")
        print(e)

# ------------------------------------------------------------
# START WS THREAD (NON DAEMON)
# ------------------------------------------------------------
print("🧵 Starting WS thread")
ws_thread = threading.Thread(target=start_ws)
ws_thread.start()

# ------------------------------------------------------------
# START FLASK (RENDER NEEDS PORT)
# ------------------------------------------------------------
port = int(os.getenv("PORT", "10000"))
print(f"🌐 Starting Flask on port {port}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
