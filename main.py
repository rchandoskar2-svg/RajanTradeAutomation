# ============================================================
# RajanTradeAutomation – main.py (Render Stable WS Version)
# FIXED: setuptools<81, FYERS WS, Render-safe threading
# + ADDED: FYERS CALLBACK URI ROUTE
# + ADDED: FYERS REDIRECT URI (v3)
# ============================================================

import os
import time
import threading
from flask import Flask, jsonify, request

# ------------------------------------------------------------
# Basic Logs
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
# Flask App (Render keep-alive)
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({
        "status": "ok",
        "service": "RajanTradeAutomation"
    })

# ------------------------------------------------------------
# FYERS CALLBACK (OLD – KEEP AS IS)
# ------------------------------------------------------------
@app.route("/callback")
def fyers_callback():
    auth_code = request.args.get("auth_code")
    print("🔑 FYERS CALLBACK HIT")
    print("🔑 AUTH CODE =", auth_code)

    if not auth_code:
        return jsonify({"error": "auth_code missing"}), 400

    return jsonify({
        "status": "callback_received",
        "auth_code": auth_code
    })

# ------------------------------------------------------------
# FYERS REDIRECT URI (NEW – v3 compatible)
# ------------------------------------------------------------
@app.route("/fyers-redirect")
def fyers_redirect():
    auth_code = request.args.get("auth_code") or request.args.get("code")
    state = request.args.get("state")

    print("🔑 FYERS REDIRECT HIT")
    print("🔑 AUTH CODE =", auth_code)
    print("🔑 STATE =", state)

    if not auth_code:
        return jsonify({"error": "auth_code missing"}), 400

    return jsonify({
        "status": "redirect_received",
        "auth_code": auth_code,
        "state": state
    })

# ------------------------------------------------------------
# FYERS WebSocket
# ------------------------------------------------------------
print("📦 Importing fyers_apiv3 WebSocket")
from fyers_apiv3.FyersWebsocket import data_ws
print("✅ data_ws IMPORT SUCCESS")

# ------------------------------------------------------------
# WebSocket Callbacks (UNCHANGED)
# ------------------------------------------------------------
def on_message(message):
    print("📩 WS MESSAGE:", message)

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
# Start WebSocket (NON-BLOCKING) – UNCHANGED
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
# Launch WS in daemon thread
# ------------------------------------------------------------
ws_thread = threading.Thread(target=start_ws, daemon=True)
ws_thread.start()

# ------------------------------------------------------------
# Start Flask (MAIN THREAD)
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Starting Flask on port {port}")
    app.run(host="0.0.0.0", port=port)
