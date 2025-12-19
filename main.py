# ============================================================
# RajanTradeAutomation – main.py (FINAL PHASE-A)
# LIVE FYERS WS + 5m Candle + Google Sheets Push
# ============================================================

import os, time, threading, requests
from datetime import datetime
from flask import Flask, jsonify, request
from fyers_apiv3.FyersWebsocket import data_ws

# -------- ENV --------
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")   # <-- MUST SET on Render

# -------- FLASK --------
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({"status":"ok"})

@app.route("/callback")
def callback():
    return jsonify({"ok":True})

# -------- CANDLE ENGINE (LOCKED) --------
CANDLE_INTERVAL = 300
candles = {}
last_candle_vol = {}

def get_start(ts):
    return ts - (ts % CANDLE_INTERVAL)

def close_candle(symbol, c):
    prev = last_candle_vol.get(symbol, c["cum_vol"])
    vol = c["cum_vol"] - prev
    last_candle_vol[symbol] = c["cum_vol"]

    payload = {
        "action": "pushCandle",
        "payload": {
            "candles": [{
                "symbol": symbol,
                "time": datetime.fromtimestamp(c["start"]).strftime("%Y-%m-%d %H:%M:%S"),
                "timeframe": "5m",
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": vol
            }]
        }
    }

    try:
        requests.post(WEBAPP_URL, json=payload, timeout=5)
        print("📤 Candle pushed:", symbol)
    except Exception as e:
        print("❌ Push failed:", e)

def update_from_tick(msg):
    symbol = msg.get("symbol")
    ltp = msg.get("ltp")
    vol = msg.get("vol_traded_today")
    ts  = msg.get("exch_feed_time")

    if not symbol or ltp is None or vol is None or ts is None:
        return

    start = get_start(ts)
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
    c["low"]  = min(c["low"], ltp)
    c["close"] = ltp
    c["cum_vol"] = vol

# -------- WS CALLBACKS --------
def on_message(msg):
    print("📩", msg)
    update_from_tick(msg)

def on_connect():
    fyers_ws.subscribe(
        symbols=[
            "NSE:SBIN-EQ","NSE:RELIANCE-EQ",
            "NSE:VEDL-EQ","NSE:AXISBANK-EQ",
            "NSE:KOTAKBANK-EQ"
        ],
        data_type="SymbolUpdate"
    )

# -------- START WS --------
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

# -------- RUN --------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
