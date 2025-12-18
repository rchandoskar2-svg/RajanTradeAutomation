# ============================================================
# RajanTradeAutomation – FYERS WS HARD DEBUG MODE
# Purpose: Identify exact WS failure point on Render
# ============================================================

from flask import Flask
import os
import time
import threading
from datetime import datetime
import traceback

print("🚀 main.py STARTED")

# ------------------------------------------------------------
# ENV CHECK
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

print("🔐 ENV CHECK")
print("WEBAPP_URL:", "SET" if WEBAPP_URL else "MISSING")
print("FYERS_ACCESS_TOKEN prefix:", FYERS_ACCESS_TOKEN[:20] if FYERS_ACCESS_TOKEN else "MISSING")

if not FYERS_ACCESS_TOKEN:
    raise Exception("❌ FYERS_ACCESS_TOKEN missing")

# ------------------------------------------------------------
# FLASK
app = Flask(__name__)

@app.route("/", methods=["GET"])
def root():
    return "FYERS WS DEBUG MODE RUNNING", 200

@app.route("/ping", methods=["GET"])
def ping():
    return "PONG", 200

# ------------------------------------------------------------
# IMPORT WS (DEBUG)
try:
    print("📦 Importing fyers_apiv3.FyersWebsocket.data_ws")
    from fyers_apiv3.FyersWebsocket import data_ws
    print("✅ data_ws import SUCCESS")
except Exception as e:
    print("❌ data_ws import FAILED")
    traceback.print_exc()
    raise

# ------------------------------------------------------------
SYMBOLS = [
    "NSE:SBIN-EQ",
    "NSE:VEDL-EQ",
    "NSE:RELIANCE-EQ",
    "NSE:AXISBANK-EQ",
    "NSE:KOTAKBANK-EQ",
]

# ------------------------------------------------------------
def onopen():
    print("✅✅✅ FYERS WS CONNECTED")
    print("📡 Subscribed symbols:", SYMBOLS)

def onerror(e):
    print("❌❌❌ WS ERROR:")
    print(e)

def onclose():
    print("⚠️⚠️⚠️ WS CLOSED")

def onmessage(msg):
    if isinstance(msg, dict):
        sym = msg.get("symbol")
        ltp = msg.get("ltp")
        if sym and ltp:
            print(f"📈 TICK {sym} LTP={ltp}")

# ------------------------------------------------------------
def start_ws():
    print("🚀 start_ws() THREAD ENTERED")

    try:
        print("🔌 Creating FyersDataSocket()")
        ws = data_ws.FyersDataSocket(
            access_token=FYERS_ACCESS_TOKEN,
            log_path="",
            litemode=False,
            write_to_file=False,
            reconnect=True,
            on_connect=onopen,
            on_message=onmessage,
            on_error=onerror,
            on_close=onclose
        )
        print("✅ FyersDataSocket object CREATED")

        print("📡 Calling subscribe()")
        ws.subscribe(symbols=SYMBOLS, data_type="SymbolUpdate")
        print("✅ subscribe() CALLED")

        print("🔁 Calling keep_running()")
        ws.keep_running()

        print("❗ keep_running EXITED (should not happen)")

    except Exception as e:
        print("❌ EXCEPTION INSIDE start_ws")
        traceback.print_exc()

# ------------------------------------------------------------
if __name__ == "__main__":
    print("🧵 Starting WS thread (NON-daemon)")
    ws_thread = threading.Thread(target=start_ws)
    ws_thread.start()

    print("🌐 Starting Flask server")
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
