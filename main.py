# ============================================================
# RajanTradeAutomation – main.py (FINAL ORCHESTRATOR)
# ============================================================

import os
import threading
from flask import Flask, jsonify, request
from fyers_apiv3.FyersWebsocket import data_ws

from ws_client import enqueue_tick
from candle_engine import start_candle_engine

print("🚀 RajanTradeAutomation STARTING (ORCHESTRATOR MODE)")

# ------------------------------------------------------------
# ENV
# ------------------------------------------------------------
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")
if not FYERS_ACCESS_TOKEN:
    raise Exception("❌ FYERS_ACCESS_TOKEN missing")

# ------------------------------------------------------------
# Flask (keep-alive + FYERS callback)
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def root():
    return jsonify({"status": "LIVE"})

@app.route("/ping")
def ping():
    return "PONG"

@app.route("/callback")
def fyers_callback():
    return "FYERS CALLBACK OK"

# ------------------------------------------------------------
# FYERS WS CALLBACKS
# ------------------------------------------------------------
def on_message(msg):
    try:
        enqueue_tick(
            symbol=msg.get("symbol"),
            ltp=msg.get("ltp"),
            volume=msg.get("vol_traded_today"),
            exch_ts=msg.get("exch_feed_time")
        )
    except Exception as e:
        print("❌ enqueue_tick error:", e)

def on_connect():
    print("🔗 FYERS WS CONNECTED")

    symbols = list(start_candle_engine())  # returns subscribed symbols
    print("📡 Subscribing:", len(symbols))

    fyers_ws.subscribe(
        symbols=symbols,
        data_type="SymbolUpdate"
    )

def on_error(err):
    print("❌ WS ERROR:", err)

def on_close():
    print("🔌 WS CLOSED")

# ------------------------------------------------------------
# WS THREAD
# ------------------------------------------------------------
def start_ws():
    global fyers_ws

    fyers_ws = data_ws.FyersDataSocket(
        access_token=FYERS_ACCESS_TOKEN,
        on_message=on_message,
        on_connect=on_connect,
        on_error=on_error,
        on_close=on_close,
        reconnect=True
    )

    fyers_ws.connect()

# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
if __name__ == "__main__":
    threading.Thread(target=start_ws, daemon=True).start()

    port = int(os.getenv("PORT", 10000))
    print(f"🌐 Flask on {port}")
    app.run(host="0.0.0.0", port=port)
