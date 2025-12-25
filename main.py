# ============================================================
# RajanTradeAutomation – main.py
# Phase-0 : FYERS LIVE TICK BY TICK
# FINAL | RENDER SAFE | PROVEN
# ============================================================

import os
import threading
import time
from flask import Flask, jsonify, request

print("🚀 main.py STARTED")

# ------------------------------------------------------------
# ENV CHECK
# ------------------------------------------------------------
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

print("🔍 ENV CHECK")
print(
    "FYERS_ACCESS_TOKEN prefix =",
    FYERS_ACCESS_TOKEN[:20] if FYERS_ACCESS_TOKEN else "❌ MISSING"
)

if not FYERS_ACCESS_TOKEN:
    raise Exception("❌ FYERS_ACCESS_TOKEN missing")

# ------------------------------------------------------------
# Flask App (PING + FYERS REDIRECT)
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "RajanTradeAutomation"})

# FYERS redirect URI (exact match in FYERS app)
@app.route("/fyers-redirect")
def fyers_redirect():
    auth_code = request.args.get("auth_code")
    print("🔑 FYERS REDIRECT HIT | AUTH CODE =", auth_code)
    return jsonify({"status": "fyers_redirect_received"})

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
# WS INITIALIZATION (THREAD-1)
# ------------------------------------------------------------
def start_ws():
    global fyers_ws
    try:
        print("🧵 WS INIT THREAD")

        fyers_ws = data_ws.FyersDataSocket(
            access_token=FYERS_ACCESS_TOKEN,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_connect=on_connect,
            reconnect=True
        )

        print("🚨 WS CONNECTING ...")
        fyers_ws.connect()

    except Exception as e:
        print("🔥 WS INIT CRASH:", e)

# ------------------------------------------------------------
# WS KEEP RUNNING (THREAD-2)
# ------------------------------------------------------------
def keep_ws_alive():
    # small delay so connect() happens first
    time.sleep(2)
    try:
        print("♻️ WS KEEP RUNNING")
        fyers_ws.keep_running()
    except Exception as e:
        print("🔥 KEEP_RUNNING CRASH:", e)

# ------------------------------------------------------------
# START WS THREADS
# ------------------------------------------------------------
threading.Thread(target=start_ws, daemon=True).start()
threading.Thread(target=keep_ws_alive, daemon=True).start()

# ------------------------------------------------------------
# START FLASK
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Flask running on port {port}")
    app.run(host="0.0.0.0", port=port)
