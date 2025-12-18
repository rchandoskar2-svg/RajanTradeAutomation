# ============================================================
# RajanTradeAutomation – Render Stable main.py
# FYERS WebSocket + Flask Ping Server
# ============================================================

import os
import time
import threading
import traceback
from flask import Flask, jsonify

print("🚀 main.py STARTED")

# ------------------------------------------------------------
# ENV CHECK
# ------------------------------------------------------------
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

print("🔍 ENV CHECK")
print("FYERS_CLIENT_ID =", FYERS_CLIENT_ID)
print("FYERS_ACCESS_TOKEN prefix =", FYERS_ACCESS_TOKEN[:15] if FYERS_ACCESS_TOKEN else "MISSING")

if not FYERS_CLIENT_ID or not FYERS_ACCESS_TOKEN:
    raise RuntimeError("❌ FYERS ENV variables missing")

# ------------------------------------------------------------
# Flask App (Render Ping / UptimeRobot)
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/", methods=["GET", "HEAD"])
def home():
    return jsonify({"ok": True, "status": "alive"})

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"pong": True})

# ------------------------------------------------------------
# FYERS WebSocket
# ------------------------------------------------------------
from fyers_apiv3.FyersWebsocket import data_ws

def on_message(message):
    print("📩 WS MESSAGE:", message)

def on_error(error):
    print("❌ WS ERROR:", error)

def on_close(message):
    print("🔌 WS CLOSED:", message)

def start_ws():
    try:
        print("🧵 WS THREAD STARTED")

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

        symbols = [
            "NSE:SBIN-EQ",
            "NSE:RELIANCE-EQ",
            "NSE:VEDL-EQ",
            "NSE:AXISBANK-EQ",
            "NSE:KOTAKBANK-EQ"
        ]

        print("📡 Subscribing symbols:", symbols)
        ws.subscribe(symbols=symbols, data_type="SymbolUpdate")

        print("✅ WS CONNECT CALLED")
        ws.connect()

    except Exception as e:
        print("🔥 WS THREAD CRASHED")
        traceback.print_exc()

# ------------------------------------------------------------
# START WS THREAD
# ------------------------------------------------------------
ws_thread = threading.Thread(target=start_ws, daemon=True)
ws_thread.start()

# ------------------------------------------------------------
# START FLASK (Render expects this)
# ------------------------------------------------------------
PORT = int(os.getenv("PORT", 10000))
print(f"🌐 Starting Flask on port {PORT}")

app.run(host="0.0.0.0", port=PORT, debug=False)
