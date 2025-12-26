# ============================================================
# RajanTradeAutomation – main.py
# Phase-0 : FYERS LIVE TICK BY TICK
# STABLE BASE + FYERS REDIRECT
# PING VIA WEBAPP | RENDER SAFE
# ============================================================

import os
import threading
import time
from flask import Flask, jsonify, request

print("🚀 main.py STARTED")

# ------------------------------------------------------------
# ENV CHECK (TOKEN OPTIONAL FOR REDIRECT FLOW)
# ------------------------------------------------------------
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

print("🔍 ENV CHECK")
print(
    "FYERS_ACCESS_TOKEN prefix =",
    FYERS_ACCESS_TOKEN[:20] if FYERS_ACCESS_TOKEN else "❌ NOT SET"
)

# ------------------------------------------------------------
# Flask App
# ------------------------------------------------------------
app = Flask(__name__)

# ---- Health / Ping (WebApp uses this) ----
@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "RajanTradeAutomation"})

# ------------------------------------------------------------
# FYERS REDIRECT URI (FOR ACCESS TOKEN GENERATION)
# ------------------------------------------------------------
@app.route("/fyers-redirect")
def fyers_redirect():
    auth_code = request.args.get("auth_code")
    state = request.args.get("state")

    print("🔑 FYERS REDIRECT HIT")
    print("   auth_code =", auth_code)
    print("   state     =", state)

    return jsonify({
        "status": "fyers_redirect_received",
        "auth_code": auth_code,
        "state": state
    })

# ------------------------------------------------------------
# FYERS WebSocket (OLD STABLE LOGIC)
# ------------------------------------------------------------
print("📦 Importing fyers_apiv3 WebSocket")
from fyers_apiv3.FyersWebsocket import data_ws
print("✅ data_ws IMPORT SUCCESS")

SUBSCRIBED_SYMBOLS = [
    "NSE:SBIN-EQ",
    "NSE:RELIANCE-EQ",
    "NSE:VEDL-EQ",
    "NSE:AXISBANK-EQ",
    "NSE:KOTAKBANK-EQ"
]

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
    print("📡 Subscribing symbols:", SUBSCRIBED_SYMBOLS)

    fyers_ws.subscribe(
        symbols=SUBSCRIBED_SYMBOLS,
        data_type="SymbolUpdate"
    )

# ------------------------------------------------------------
# WS THREAD-1 : INIT + CONNECT
# ------------------------------------------------------------
def start_ws():
    global fyers_ws
    try:
        if not FYERS_ACCESS_TOKEN:
            print("⚠️ FYERS_ACCESS_TOKEN not set – WS skipped (redirect mode)")
            return

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
# WS THREAD-2 : KEEP RUNNING
# ------------------------------------------------------------
def keep_ws_alive():
    time.sleep(2)
    try:
        if FYERS_ACCESS_TOKEN:
            print("♻️ WS KEEP RUNNING")
            fyers_ws.keep_running()
    except Exception as e:
        print("🔥 KEEP_RUNNING CRASH:", e)

threading.Thread(target=start_ws, daemon=True).start()
threading.Thread(target=keep_ws_alive, daemon=True).start()

# ------------------------------------------------------------
# START FLASK (RENDER SAFE)
# ------------------------------------------------------------
port = int(os.environ.get("PORT", 10000))
print(f"🌐 Flask running on port {port}")
app.run(host="0.0.0.0", port=port)
