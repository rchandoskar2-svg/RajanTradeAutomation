# ============================================================
# RajanTradeAutomation – main.py (TIME-GATED TICK ENGINE)
# WS ALWAYS ON | TICKS PROCESSED ONLY AFTER TICK_START_TIME
# ============================================================

import os
import time
import json
import threading
import requests
from datetime import datetime, time as dtime
from flask import Flask, jsonify, request

print("🚀 main.py STARTED")

# ------------------------------------------------------------
# ENV
# ------------------------------------------------------------
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")

if not FYERS_ACCESS_TOKEN or not WEBAPP_URL:
    raise Exception("ENV missing")

# ------------------------------------------------------------
# GLOBAL TIME CONFIG (loaded from Settings)
# ------------------------------------------------------------
TICK_START_TIME = None
BIAS_TIME = None

def parse_time(tstr):
    h, m, s = map(int, tstr.split(":"))
    return dtime(h, m, s)

def load_settings():
    global TICK_START_TIME, BIAS_TIME

    try:
        url = WEBAPP_URL.rstrip("/") + "/getSettings"
        resp = requests.get(url, timeout=10)
        data = resp.json()

        TICK_START_TIME = parse_time(data["TICK_START_TIME"])
        BIAS_TIME = parse_time(data["BIAS_TIME"])

        print("✅ SETTINGS LOADED")
        print("TICK_START_TIME =", TICK_START_TIME)
        print("BIAS_TIME =", BIAS_TIME)

    except Exception as e:
        print("❌ SETTINGS LOAD FAILED:", e)
        raise

load_settings()

# ------------------------------------------------------------
# Flask
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def health():
    return "OK", 200

@app.route("/ping")
def ping():
    return "pong", 200

@app.route("/fyers-redirect", methods=["GET"])
def fyers_redirect():
    auth_code = request.args.get("auth_code") or request.args.get("code")
    print("🔑 FYERS REDIRECT auth_code =", auth_code)
    return jsonify({"auth_code": auth_code})

# ------------------------------------------------------------
# FYERS WS
# ------------------------------------------------------------
from fyers_apiv3.FyersWebsocket import data_ws

# ------------------------------------------------------------
# 5-MIN CANDLE ENGINE (CORRECT VOLUME)
# ------------------------------------------------------------
CANDLE_INTERVAL = 300

candles = {}
last_cum_vol = {}

def candle_start(ts):
    return ts - (ts % CANDLE_INTERVAL)

def close_candle(symbol, c):
    prev = last_cum_vol.get(symbol)
    vol = c["cum_vol"] if prev is None else c["cum_vol"] - prev
    last_cum_vol[symbol] = c["cum_vol"]

    print(
        f"\n🟩 5m CANDLE {symbol}"
        f"\nTime: {time.strftime('%H:%M:%S', time.localtime(c['start']))}"
        f"\nO:{c['open']} H:{c['high']} L:{c['low']} "
        f"C:{c['close']} V:{vol}"
        f"\n---------------------"
    )

def update_from_tick(msg):
    symbol = msg.get("symbol")
    ltp = msg.get("ltp")
    cum_vol = msg.get("vol_traded_today")
    ts = msg.get("exch_feed_time")

    if not symbol or ltp is None or cum_vol is None or ts is None:
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
            "cum_vol": cum_vol
        }
        return

    c["high"] = max(c["high"], ltp)
    c["low"] = min(c["low"], ltp)
    c["close"] = ltp
    c["cum_vol"] = cum_vol

# ------------------------------------------------------------
# WS CALLBACK (TIME-GATED TICKS)
# ------------------------------------------------------------
def on_message(msg):
    now = datetime.now().time()

    # 🔒 CORE RULE: ticks ignored before TICK_START_TIME
    if now < TICK_START_TIME:
        return

    try:
        update_from_tick(msg)
    except Exception as e:
        print("🔥 candle error:", e)

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
    print("📡 SUBSCRIBED")

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

# ------------------------------------------------------------
# Start Flask
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
