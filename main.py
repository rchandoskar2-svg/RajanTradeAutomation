# ============================================================
# RajanTradeAutomation – main.py
# Phase-0 : FYERS LIVE TICK BY TICK (ONLY)
# Render SAFE | MINIMAL | STABLE
# ============================================================

import os
import threading
from flask import Flask, jsonify, request

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
# Flask App (PING + CALLBACK)
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "RajanTradeAutomation"})

@app.route("/callback")
def fyers_callback():
    auth_code = request.args.get("auth_code")
    print("🔑 FYERS CALLBACK HIT | AUTH CODE =", auth_code)
    return jsonify({"status": "callback_received"})

# ------------------------------------------------------------
# FYERS WebSocket
# ------------------------------------------------------------
print("📦 Importing fyers_apiv3 WebSocket")
from fyers_apiv3.FyersWebsocket import data_ws
print("✅ data_ws IMPORT SUCCESS")

# ------------------------------------------------------------
# WS CALLBACKS
# ------------------------------------------------------------
def on_message(message):
    """
    Tick-by-tick data comes here.
    Ignore non-tick payloads.
    """
    if isinstance(message, dict) and "symbol" in message:
        print("📩 TICK:", {
            "symbol": message.get("symbol"),
            "ltp": message.get("ltp"),
            "vol": message.get("vol_traded_today"),
            "time": message.get("exch_feed_time")
        })

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
# WS THREAD (CRITICAL FIX)
# ------------------------------------------------------------
def start_ws():
    global fyers_ws
    try:
        print("🧵 WS THREAD STARTED")

        fyers_ws = data_ws.FyersDataSocket(
            access_token=FYERS_ACCESS_TOKEN,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_connect=on_connect,
            reconnect=True
        )

        print("🚨 CALLING WS CONNECT")
        fyers_ws.connect()

        # 🔥 MOST IMPORTANT FOR RENDER
        fyers_ws.keep_running()

    except Exception as e:
        print("🔥 WS THREAD CRASHED:", e)

# ------------------------------------------------------------
# START WS
# ------------------------------------------------------------
threading.Thread(target=start_ws, daemon=True).start()

# ------------------------------------------------------------
# START FLASK
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Flask running on port {port}")
    app.run(host="0.0.0.0", port=port)
