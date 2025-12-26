# ============================================================
# RajanTradeAutomation – main.py
# Phase-0 : FYERS LIVE TICK BY TICK
# FINAL STABLE BASE (LOCK)
# - FYERS v3 Redirect URI
# - Render-safe WS threading
# - Proven 5-min candle (cum volume)
# ============================================================

import os
import time
import threading
from flask import Flask, jsonify, request

# ------------------------------------------------------------
# BOOT LOG
# ------------------------------------------------------------
print("🚀 main.py STARTED")

# ------------------------------------------------------------
# ENV CHECK
# ------------------------------------------------------------
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

print("🔍 ENV CHECK")
print(
    "FYERS_ACCESS_TOKEN prefix =",
    FYERS_ACCESS_TOKEN[:20] if FYERS_ACCESS_TOKEN else "❌ NOT SET"
)

# NOTE:
# Access token नसला तरी app crash होऊ नये
# Redirect + ping साठी service चालू राहिली पाहिजे

# ------------------------------------------------------------
# Flask App (WebApp Ping + FYERS Redirect)
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({
        "status": "ok",
        "service": "RajanTradeAutomation"
    })

# ------------------------------------------------------------
# FYERS REDIRECT URI (v3 compatible)
# ------------------------------------------------------------
@app.route("/fyers-redirect", methods=["GET"])
def fyers_redirect():
    auth_code = request.args.get("auth_code") or request.args.get("code")
    state = request.args.get("state")

    print("🔑 FYERS REDIRECT HIT")
    print("auth_code =", auth_code)
    print("state     =", state)

    if not auth_code:
        return jsonify({"error": "auth_code missing"}), 400

    return jsonify({
        "status": "fyers_redirect_received",
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
# 5-MIN CANDLE ENGINE (LOCKED LOGIC)
# ------------------------------------------------------------
CANDLE_INTERVAL = 300  # 5 minutes

candles = {}          # symbol -> running candle
last_candle_vol = {}  # symbol -> last candle cumulative volume

def candle_start(ts):
    return ts - (ts % CANDLE_INTERVAL)

def close_candle(symbol, c):
    prev_vol = last_candle_vol.get(symbol, c["cum_vol"])
    candle_vol = c["cum_vol"] - prev_vol
    last_candle_vol[symbol] = c["cum_vol"]

    print(
        f"\n🟩 5m CANDLE {symbol}"
        f"\nTime : {time.strftime('%H:%M:%S', time.localtime(c['start']))}"
        f"\nO:{c['open']} H:{c['high']} L:{c['low']} "
        f"C:{c['close']} V:{candle_vol}"
        f"\n---------------------------"
    )

def update_candle(tick):
    if not isinstance(tick, dict):
        return

    symbol = tick.get("symbol")
    ltp = tick.get("ltp")
    vol = tick.get("vol_traded_today")
    ts = tick.get("exch_feed_time")

    if not symbol or ltp is None or vol is None or ts is None:
        return

    start = candle_start(ts)
    c = candles.get(symbol)

    # New candle
    if c is None or c["start"] != start:
        if c:
            close_candle(symbol, c)

        candles[symbol] = {
            "start": start,
            "open": ltp,
            "high": ltp,
            "low": ltp,
            "close": ltp,
            "cum_vol": vol
        }
        return

    # Update running candle
    c["high"] = max(c["high"], ltp)
    c["low"] = min(c["low"], ltp)
    c["close"] = ltp
    c["cum_vol"] = vol

# ------------------------------------------------------------
# WS CALLBACKS
# ------------------------------------------------------------
def on_message(msg):
    try:
        update_candle(msg)
    except Exception as e:
        print("🔥 Candle error:", e)

def on_error(msg):
    print("❌ WS ERROR:", msg)

def on_close(msg):
    print("🔌 WS CLOSED:", msg)

def on_connect():
    print("🔗 WS CONNECTED")

    symbols = [
        "NSE:SBIN-EQ",
        "NSE:RELIANCE-EQ",
        "NSE:VEDL-EQ",
        "NSE:AXISBANK-EQ",
        "NSE:KOTAKBANK-EQ"
    ]

    print("📡 Subscribing:", symbols)
    fyers_ws.subscribe(symbols=symbols, data_type="SymbolUpdate")

# ------------------------------------------------------------
# WS THREAD (SAFE FOR RENDER)
# ------------------------------------------------------------
def start_ws():
    if not FYERS_ACCESS_TOKEN:
        print("⚠️ Access token missing – WS not started")
        return

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

        fyers_ws.connect()
        fyers_ws.keep_running()

    except Exception as e:
        print("🔥 WS THREAD CRASH:", e)

threading.Thread(target=start_ws, daemon=True).start()

# ------------------------------------------------------------
# START FLASK (RENDER MAIN THREAD)
# ------------------------------------------------------------
port = int(os.environ.get("PORT", 10000))
print(f"🌐 Flask running on port {port}")
app.run(host="0.0.0.0", port=port)
