# ============================================================
# RajanTradeAutomation – Render WS Debug Stable
# ============================================================

import os
import threading
import time
import traceback
from flask import Flask

# ------------------------------------------------------------
# BASIC LOG
# ------------------------------------------------------------
def log(msg):
    print(msg, flush=True)

log("🚀 main.py STARTED")

# ------------------------------------------------------------
# ENV CHECK
# ------------------------------------------------------------
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

log("🔎 ENV CHECK")
log(f"FYERS_CLIENT_ID = {FYERS_CLIENT_ID}")
log(f"FYERS_ACCESS_TOKEN prefix = {FYERS_ACCESS_TOKEN[:20] if FYERS_ACCESS_TOKEN else 'MISSING'}")

if not FYERS_CLIENT_ID or not FYERS_ACCESS_TOKEN:
    log("❌ FYERS ENV MISSING – EXITING")
    raise Exception("Missing FYERS env variables")

# ------------------------------------------------------------
# IMPORT FYERS WS
# ------------------------------------------------------------
try:
    log("📦 Importing fyers_apiv3.FyersWebsocket.data_ws")
    from fyers_apiv3.FyersWebsocket import data_ws
    log("✅ data_ws IMPORT SUCCESS")
except Exception as e:
    log("❌ data_ws IMPORT FAILED")
    traceback.print_exc()
    raise e

# ------------------------------------------------------------
# FLASK (KEEP RENDER ALIVE)
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "RajanTradeAutomation LIVE"

@app.route("/ping")
def ping():
    return "PONG"

# ------------------------------------------------------------
# FYERS CALLBACKS
# ------------------------------------------------------------
def on_open():
    log("🟢 WS CONNECTED (on_open called)")

def on_close(message):
    log(f"🔴 WS CLOSED : {message}")

def on_error(message):
    log(f"❌ WS ERROR : {message}")

def on_message(message):
    log(f"📩 WS MESSAGE : {message}")

# ------------------------------------------------------------
# START FYERS WS
# ------------------------------------------------------------
def start_ws():
    try:
        log("🧠 Creating FyersDataSocket")

        ws = data_ws.FyersDataSocket(
            access_token=FYERS_ACCESS_TOKEN,
            log_path="",
            litemode=False,
            write_to_file=False,
            reconnect=True,
            on_open=on_open,
            on_close=on_close,
            on_error=on_error,
            on_message=on_message
        )

        symbols = [
            "NSE:SBIN-EQ",
            "NSE:RELIANCE-EQ",
            "NSE:VEDL-EQ",
            "NSE:AXISBANK-EQ",
            "NSE:KOTAKBANK-EQ"
        ]

        log(f"📡 Subscribing symbols: {symbols}")
        ws.subscribe(symbols=symbols, data_type="SymbolUpdate")

        log("🔁 Calling keep_running() (BLOCKING)")
        ws.keep_running()

        log("❌ keep_running EXITED (SHOULD NOT HAPPEN)")

    except Exception as e:
        log("❌ WS THREAD CRASHED")
        traceback.print_exc()

# ------------------------------------------------------------
# THREAD START
# ------------------------------------------------------------
log("🧵 Starting WS THREAD (daemon=True)")
ws_thread = threading.Thread(target=start_ws, daemon=True)
ws_thread.start()

# ------------------------------------------------------------
# START FLASK
# ------------------------------------------------------------
PORT = int(os.environ.get("PORT", 10000))
log(f"🌐 Starting Flask on port {PORT}")
app.run(host="0.0.0.0", port=PORT)
