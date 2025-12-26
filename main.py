# ============================================================
# RajanTradeAutomation – main.py
# Phase-0 : FYERS LIVE TICK BY TICK + 5 MIN CANDLE
#
# NSE  -> SymbolUpdate (ltp direct)
# MCX  -> DepthUpdate  (ltp derived from bid/ask)
# FIX  -> Timer based candle close (for MCX reliability)
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

if not FYERS_CLIENT_ID or not FYERS_ACCESS_TOKEN:
    raise Exception("❌ FYERS ENV variables missing")

# ------------------------------------------------------------
# Flask App
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({"status": "ok"})

# ------------------------------------------------------------
# FYERS WebSocket
# ------------------------------------------------------------
from fyers_apiv3.FyersWebsocket import data_ws

# ------------------------------------------------------------
# 5-MIN CANDLE ENGINE
# ------------------------------------------------------------
CANDLE_INTERVAL = 300  # 5 minutes

candles = {}          # symbol -> running candle
last_candle_vol = {}  # symbol -> last cumulative volume

def candle_start(ts):
    return ts - (ts % CANDLE_INTERVAL)

def close_candle(symbol, c):
    prev_vol = last_candle_vol.get(symbol, c["cum_vol"])
    candle_vol = c["cum_vol"] - prev_vol
    last_candle_vol[symbol] = c["cum_vol"]

    print(
        f"\n🟩 5m CANDLE CLOSED | {symbol}"
        f"\nTime : {time.strftime('%H:%M:%S', time.localtime(c['start']))}"
        f"\nO:{c['open']} H:{c['high']} L:{c['low']} "
        f"C:{c['close']} V:{candle_vol}"
        f"\n-------------------------------"
    )

def update_candle_from_tick(msg):
    if not isinstance(msg, dict):
        return

    symbol = msg.get("symbol")
    if not symbol:
        return

    # ---------------- PRICE ----------------
    ltp = msg.get("ltp")

    if ltp is None:
        bid = msg.get("bid_price1")
        ask = msg.get("ask_price1")
        if bid is not None and ask is not None:
            ltp = (bid + ask) / 2
        else:
            return

    # ---------------- TIME ----------------
    ts = msg.get("exch_feed_time") or msg.get("last_traded_time")
    if ts is None:
        return

    vol = msg.get("vol_traded_today", 0)

    start = candle_start(ts)
    c = candles.get(symbol)

    if c is None:
        candles[symbol] = {
            "start": start,
            "open": ltp,
            "high": ltp,
            "low": ltp,
            "close": ltp,
            "cum_vol": vol
        }
        return

    if c["start"] != start:
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
# 🔥 TIMER-BASED FORCE CLOSE (KEY FIX)
# ------------------------------------------------------------
def force_candle_close_timer():
    while True:
        now = int(time.time())
        current_bucket = candle_start(now)

        for symbol, c in list(candles.items()):
            if c and c["start"] < current_bucket:
                close_candle(symbol, c)
                candles[symbol] = None

        time.sleep(20)  # safe interval

# ------------------------------------------------------------
# WebSocket Callbacks
# ------------------------------------------------------------
def on_message(message):
    print("📩 TICK:", message)
    update_candle_from_tick(message)

def on_error(message):
    print("❌ WS ERROR:", message)

def on_close(message):
    print("🔌 WS CLOSED:", message)

def on_connect():
    print("🔗 WS CONNECTED")

    # NSE STOCKS (UNCHANGED)
    stock_symbols = [
        "NSE:SBIN-EQ",
        "NSE:RELIANCE-EQ",
        "NSE:VEDL-EQ",
        "NSE:AXISBANK-EQ",
        "NSE:KOTAKBANK-EQ"
    ]

    # MCX CRUDE OIL
    crude_symbol = "MCX:CRUDEOIL26JANFUT"

    fyers_ws.subscribe(
        symbols=stock_symbols,
        data_type="SymbolUpdate"
    )

    fyers_ws.subscribe(
        symbols=[crude_symbol],
        data_type="DepthUpdate"
    )

# ------------------------------------------------------------
# Start WebSocket
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

    fyers_ws.connect()

threading.Thread(target=start_ws, daemon=True).start()
threading.Thread(target=force_candle_close_timer, daemon=True).start()

# ------------------------------------------------------------
# Start Flask
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
