# ============================================================
# RajanTradeAutomation – main.py
# Phase-0 : FYERS LIVE TICK BY TICK
# FINAL | RENDER SAFE | PROVEN
# + TEST SECTOR BIAS ROUTE
# ============================================================

import os
import threading
import time
from flask import Flask, jsonify, request
from datetime import datetime

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

# --- CURRENT 5 STOCK UNIVERSE ---
SUBSCRIBED_SYMBOLS = [
    "NSE:SBIN-EQ",
    "NSE:RELIANCE-EQ",
    "NSE:VEDL-EQ",
    "NSE:AXISBANK-EQ",
    "NSE:KOTAKBANK-EQ"
]

def on_connect():
    print("🔗 WS CONNECTED")
    print("📡 Subscribing symbols:", SUBSCRIBED_SYMBOLS)

    fyers_ws.subscribe(
        symbols=SUBSCRIBED_SYMBOLS,
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
    time.sleep(2)
    try:
        print("♻️ WS KEEP RUNNING")
        fyers_ws.keep_running()
    except Exception as e:
        print("🔥 KEEP_RUNNING CRASH:", e)

threading.Thread(target=start_ws, daemon=True).start()
threading.Thread(target=keep_ws_alive, daemon=True).start()

# ------------------------------------------------------------
# 🔍 TEST SECTOR BIAS ROUTE (DRY RUN)
# ------------------------------------------------------------
from sector_engine import run_sector_bias

SECTOR_LINKS = {
    "NIFTY AUTO": "https://www.nseindia.com/market-data/live-equity-market?symbol=NIFTY%20AUTO",
    "NIFTY FMCG": "https://www.nseindia.com/market-data/live-equity-market?symbol=NIFTY%20FMCG",
    "NIFTY IT": "https://www.nseindia.com/market-data/live-equity-market?symbol=NIFTY%20IT",
    "NIFTY METAL": "https://www.nseindia.com/market-data/live-equity-market?symbol=NIFTY%20METAL",
    "NIFTY PHARMA": "https://www.nseindia.com/market-data/live-equity-market?symbol=NIFTY%20PHARMA"
}

@app.route("/test-sector-bias")
def test_sector_bias():
    start_time = datetime.now().strftime("%H:%M:%S")

    strong_sectors, selected = run_sector_bias(SECTOR_LINKS)

    all_symbols = {s.split(":")[1].replace("-EQ", "") for s in SUBSCRIBED_SYMBOLS}
    selected_set = set(selected)
    drop_preview = sorted(all_symbols - selected_set)

    return jsonify({
        "test_time": start_time,
        "current_universe_size": len(all_symbols),
        "strong_sectors": strong_sectors,
        "selected_stocks": selected,
        "selected_count": len(selected),
        "unsubscribe_preview": drop_preview,
        "note": "DRY RUN ONLY – NO WS UNSUBSCRIBE EXECUTED"
    })

# ------------------------------------------------------------
# START FLASK
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Flask running on port {port}")
    app.run(host="0.0.0.0", port=port)
