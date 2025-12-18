# ============================================================
# RajanTradeAutomation – FYERS WS DEBUG (Render runtime pip fix)
# ============================================================

import os
import sys
import subprocess
import time
import threading
from flask import Flask

print("🚀 main.py STARTED")

# ------------------------------------------------------------
# FORCE setuptools<81 AT RUNTIME (RENDER ONLY)
# ------------------------------------------------------------
def ensure_setuptools():
    try:
        import setuptools
        ver = setuptools.__version__
        print("🔧 setuptools version detected:", ver)
        major = int(ver.split(".")[0])
        if major >= 81:
            raise Exception("setuptools too new")
    except Exception:
        print("⚠️ Installing setuptools<81 at runtime")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--no-cache-dir", "setuptools<81"]
        )
        print("✅ setuptools<81 installed, RESTART REQUIRED")
        os.execv(sys.executable, [sys.executable] + sys.argv)

ensure_setuptools()

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
    sys.exit(1)

# ------------------------------------------------------------
# IMPORT FYERS WS (AFTER SETUPTOOLS FIX)
# ------------------------------------------------------------
print("📦 Importing fyers_apiv3.FyersWebsocket.data_ws")
from fyers_apiv3.FyersWebsocket import data_ws
print("✅ data_ws IMPORT SUCCESS")

# ------------------------------------------------------------
# FLASK (RENDER HEALTH)
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "RajanTradeAutomation WS DEBUG LIVE", 200

@app.route("/ping")
def ping():
    return "PONG", 200

# ------------------------------------------------------------
# WS CALLBACKS
# ------------------------------------------------------------
def onopen():
    print("🟢 WS CONNECTED")

def onmessage(message):
    print("📩 WS MESSAGE")
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
        print("🔧 Creating FyersDataSocket")

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

        print("📡 Subscribing:", symbols)

        ws.subscribe(
            symbols=symbols,
            data_type="SymbolUpdate"
        )

        print("▶ keep_running() called (BLOCKING)")
        ws.keep_running()

        print("❌ keep_running EXITED (should NOT happen)")

    except Exception as e:
        print("🔥 WS THREAD EXCEPTION")
        print(e)

# ------------------------------------------------------------
# START WS THREAD
# ------------------------------------------------------------
print("🧵 Starting WS thread")
threading.Thread(target=start_ws, daemon=False).start()

# ------------------------------------------------------------
# START FLASK
# ------------------------------------------------------------
port = int(os.getenv("PORT", "10000"))
print("🌐 Starting Flask on port", port)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
