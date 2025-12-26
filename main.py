# ============================================================
# RajanTradeAutomation – main.py
# FINAL WS-STABLE VERSION (LOCK)
# - FYERS LIVE TICK BY TICK
# - PROVEN 5-MIN CANDLE (CUM VOL)
# - RENDER SAFE THREADING
# - FYERS REDIRECT URI
# ============================================================

import os
import time
import threading
from flask import Flask, jsonify, request

print("🚀 main.py STARTED")

# ------------------------------------------------------------
# ENV
# ------------------------------------------------------------
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

print("🔍 ENV CHECK")
print(
    "FYERS_ACCESS_TOKEN prefix =",
    FYERS_ACCESS_TOKEN[:20] if FYERS_ACCESS_TOKEN else "❌ MISSING"
)

if not FYERS_ACCESS_TOKEN:
    print("⚠️ FYERS_ACCESS_TOKEN missing – WS will not start")

# ------------------------------------------------------------
# FLASK (Ping + Redirect)
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "RajanTradeAutomation"})

@app.route("/fyers-redirect")
def fyers_redirect():
    auth_code = request.args.get("auth_code") or request.args.get("code")
    state = request.args.get("state")

    print("🔑 FYERS REDIRECT HIT")
    print("auth_code =", auth_code)
    print("state     =", state)

    return jsonify({
        "status": "fyers_redirect_received",
        "auth_code": auth_code,
        "state": state
    })

# ------------------------------------------------------------
# FYERS WS
# ------------------------------------------------------------
print("📦 Importing fyers_apiv3 WebSocket")
from fyers_apiv3.FyersWebsocket import data_ws
print("✅ data_ws IMPORT SUCCESS")

# ------------------------------------------------------------
# 5-MIN CANDLE (LOCKED LOGIC)
# ------------------------------------------------------------
CANDLE_INTERVAL = 300  # seconds

candles = {}
last_candle_vol = {}

def candle_start(ts):
    return ts - (ts % CANDLE_INTERVAL)

def close_candle(symbol, c):
    prev = last_candle_vol.get(symbol, c["cum_vol"])
    vol = c["cum_vol"] - prev
    last_candle_vol[symbol] = c["cum_vol"]

    print(
        f"\n🟩 5m CANDLE {symbol}"
        f"\nTime : {time.strftime('%H:%M:%S', time.localtime(c['start']))}"
        f"\nO:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']} V:{vol}"
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
# WS THREAD 1 – CONNECT
# ------------------------------------------------------------
def start_ws():
    global fyers_ws
    if not FYERS_ACCESS_TOKEN:
        return

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
# WS THREAD 2 – KEEP RUNNING (CRITICAL)
# ------------------------------------------------------------
def keep_ws_alive():
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
# START FLASK (MAIN THREAD)
# ------------------------------------------------------------
port = int(os.environ.get("PORT", 10000))
print(f"🌐 Flask running on port {port}")
app.run(host="0.0.0.0", port=port)
