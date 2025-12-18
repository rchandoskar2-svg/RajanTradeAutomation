# ============================================================
# RajanTradeAutomation – main.py (FINAL STABLE – Render Ready)
# FYERS API v3 WebSocket – Correct Callback Style
# ============================================================

from flask import Flask
import threading
import os
import time
import traceback

from fyers_apiv3.FyersWebsocket import data_ws

app = Flask(__name__)

# ------------------------------------------------------------
# ENV CHECK
# ------------------------------------------------------------
print("🚀 main.py STARTED")
print("🔍 ENV CHECK")

FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

if not FYERS_CLIENT_ID or not FYERS_ACCESS_TOKEN:
    raise Exception("❌ FYERS_CLIENT_ID or FYERS_ACCESS_TOKEN missing")

print("✅ FYERS_CLIENT_ID =", FYERS_CLIENT_ID)
print("✅ FYERS_ACCESS_TOKEN prefix =", FYERS_ACCESS_TOKEN[:20])

# ------------------------------------------------------------
# SYMBOLS (TEST SET)
# ------------------------------------------------------------
SYMBOLS = [
    "NSE:SBIN-EQ",
    "NSE:RELIANCE-EQ",
    "NSE:VEDL-EQ",
    "NSE:AXISBANK-EQ",
    "NSE:KOTAKBANK-EQ",
]

# ------------------------------------------------------------
# FYERS WS CALLBACKS
# ------------------------------------------------------------
def on_open():
    print("🟢 WS CONNECTED (on_open)")

def on_message(message):
    print("📩 TICK:", message)

def on_error(message):
    print("🔴 WS ERROR:", message)

def on_close(message):
    print("🔕 WS CLOSED:", message)

# ------------------------------------------------------------
# WS THREAD
# ------------------------------------------------------------
def start_ws():
    try:
        print("🔌 Creating FyersDataSocket")

        ws = data_ws.FyersDataSocket(
            access_token=FYERS_ACCESS_TOKEN,
            log_path=""
        )

        # Attach callbacks (THIS IS THE FIX)
        ws.on_open = on_open
        ws.on_message = on_message
        ws.on_error = on_error
        ws.on_close = on_close

        print("📡 Subscribing symbols:", SYMBOLS)
        ws.subscribe(symbols=SYMBOLS, data_type="SymbolUpdate")

        print("🔁 keep_running() START")
        ws.keep_running()

    except Exception as e:
        print("❌ WS THREAD CRASHED")
        traceback.print_exc()

# ------------------------------------------------------------
# START WS THREAD
# ------------------------------------------------------------
ws_thread = threading.Thread(target=start_ws, daemon=True)
ws_thread.start()
print("🧵 WS THREAD STARTED")

# ------------------------------------------------------------
# FLASK ROUTES
# ------------------------------------------------------------
@app.route("/")
def home():
    return "RajanTradeAutomation LIVE"

@app.route("/ping")
def ping():
    return "PONG"

# ------------------------------------------------------------
# START FLASK (Render needs this)
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Starting Flask on port {port}")
    app.run(host="0.0.0.0", port=port)
