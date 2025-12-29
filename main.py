# ============================================================
# RajanTradeAutomation – main.py
# Phase-0 : FYERS LIVE TICK BY TICK + 5 MIN CANDLE
# DEBUG SAFE VERSION (TICKS + CANDLES)
# ============================================================

import os
import time
import threading
from flask import Flask, jsonify, request

print("🚀 main.py STARTED")

FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

if not FYERS_CLIENT_ID or not FYERS_ACCESS_TOKEN:
    raise Exception("❌ FYERS ENV variables missing")

app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({"status": "ok"})

from fyers_apiv3.FyersWebsocket import data_ws

# ------------------------------------------------------------
# 5 MIN CANDLE ENGINE (NO FIELD ASSUMPTIONS)
# ------------------------------------------------------------
CANDLE_INTERVAL = 300
candles = {}

def candle_start(ts):
    return ts - (ts % CANDLE_INTERVAL)

def close_candle(symbol, c):
    print(
        f"\n🟩 5m CANDLE CLOSED | {symbol}"
        f"\nTime : {time.strftime('%H:%M:%S', time.localtime(c['start']))}"
        f"\nO:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']}"
        f"\n-------------------------------"
    )

def extract_price(msg):
    for key in ("ltp", "last_price", "lp", "price"):
        if key in msg and msg[key] is not None:
            return msg[key]
    return None

def extract_time(msg):
    return msg.get("exch_feed_time") or msg.get("last_traded_time")

def update_candle_from_tick(msg):
    if not isinstance(msg, dict):
        return

    symbol = msg.get("symbol")
    price = extract_price(msg)
    ts = extract_time(msg)

    if not symbol or price is None or ts is None:
        return

    start = candle_start(ts)
    c = candles.get(symbol)

    if c is None or c["start"] != start:
        if c:
            close_candle(symbol, c)

        candles[symbol] = {
            "start": start,
            "open": price,
            "high": price,
            "low": price,
            "close": price
        }
        return

    c["high"] = max(c["high"], price)
    c["low"] = min(c["low"], price)
    c["close"] = price

# ------------------------------------------------------------
# WS CALLBACKS (DEBUG MODE)
# ------------------------------------------------------------
def on_message(msg):
    print("📩 TICK:", msg)     # DEBUG ON
    update_candle_from_tick(msg)

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

def start_ws():
    global fyers_ws
    fyers_ws = data_ws.FyersDataSocket(
        access_token=FYERS_ACCESS_TOKEN,
        on_message=on_message,
        on_connect=on_connect,
        reconnect=True
    )
    fyers_ws.connect()

threading.Thread(target=start_ws, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
