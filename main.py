# ============================================================
# RajanTradeAutomation – main.py
# FYERS LIVE TICKS + 5 MIN CANDLES (SILENT)
# WS FLOW FIXED (connect + keep_running)
# ============================================================

import os
import time
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
print("FYERS_ACCESS_TOKEN prefix =", FYERS_ACCESS_TOKEN[:20])

if not FYERS_CLIENT_ID or not FYERS_ACCESS_TOKEN:
    raise Exception("❌ FYERS ENV variables missing")

# ------------------------------------------------------------
# FLASK
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({"status": "ok"})

@app.route("/fyers-redirect")
def fyers_redirect():
    auth_code = request.args.get("auth_code") or request.args.get("code")
    print("🔑 FYERS REDIRECT HIT | auth_code =", auth_code)
    return jsonify({"status": "ok", "auth_code": auth_code})

# ------------------------------------------------------------
# FYERS WS
# ------------------------------------------------------------
from fyers_apiv3.FyersWebsocket import data_ws

# ------------------------------------------------------------
# 5 MIN CANDLE ENGINE
# ------------------------------------------------------------
CANDLE_INTERVAL = 300
candles = {}
last_candle_vol = {}

def candle_start(ts):
    return ts - (ts % CANDLE_INTERVAL)

def close_candle(symbol, c):
    prev = last_candle_vol.get(symbol, c["cum_vol"])
    vol = c["cum_vol"] - prev
    last_candle_vol[symbol] = c["cum_vol"]

    print(
        f"\n🟩 5m CANDLE CLOSED | {symbol}"
        f"\nTime : {time.strftime('%H:%M:%S', time.localtime(c['start']))}"
        f"\nO:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']} V:{vol}"
        f"\n--------------------------------"
    )

def update_candle(msg):
    if not isinstance(msg, dict):
        return

    symbol = msg.get("symbol")
    ltp = msg.get("ltp")
    vol = msg.get("vol_traded_today")
    ts = msg.get("exch_feed_time")

    if not symbol or ltp is None or vol is None or ts is None:
        return

    if ts > 10_000_000_000:
        ts //= 1000

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
# WS CALLBACKS (SILENT TICKS)
# ------------------------------------------------------------
def on_message(msg):
    update_candle(msg)

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

    fyers_ws.subscribe(symbols=symbols, data_type="SymbolUpdate")

# ------------------------------------------------------------
# THREAD 1 – CONNECT
# ------------------------------------------------------------
def start_ws():
    global fyers_ws
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

# ------------------------------------------------------------
# THREAD 2 – KEEP RUNNING  ✅ FIX
# ------------------------------------------------------------
def keep_ws_alive():
    time.sleep(2)
    print("♻️ WS KEEP RUNNING")
    fyers_ws.keep_running()

threading.Thread(target=start_ws, daemon=True).start()
threading.Thread(target=keep_ws_alive, daemon=True).start()

# ------------------------------------------------------------
# START FLASK
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Flask running on port {port}")
    app.run(host="0.0.0.0", port=port)
