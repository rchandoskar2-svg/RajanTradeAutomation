# ============================================================
# RajanTradeAutomation – main.py (FINAL STABLE)
# Tick → 5m Candle → Batch Push → Bias Engine
# ============================================================

import os
import time
import json
import threading
import requests
from datetime import datetime
from flask import Flask, jsonify, request
from fyers_apiv3.FyersWebsocket import data_ws

# ------------------------------------------------------------
# ENV (Render)
# ------------------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL")
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

if not WEBAPP_URL or not FYERS_ACCESS_TOKEN:
    raise Exception("Missing ENV variables")

# ------------------------------------------------------------
# TODAY TEST TIMINGS
# ------------------------------------------------------------
TICK_START = "15:05:00"
BIAS_TIME  = "15:15:05"
STOP_TIME  = "15:30:00"
CANDLE_SEC = 300

# ------------------------------------------------------------
# SYMBOL LIST (FULL – DO NOT TRIM)
# ------------------------------------------------------------
SYMBOLS = [
    # AUTO
    "NSE:EICHERMOT-EQ","NSE:SONACOMS-EQ","NSE:TVSMOTOR-EQ","NSE:MARUTI-EQ",
    "NSE:TMPV-EQ","NSE:M&M-EQ","NSE:MOTHERSON-EQ","NSE:TIINDIA-EQ",
    "NSE:BHARATFORG-EQ","NSE:BOSCHLTD-EQ","NSE:EXIDEIND-EQ","NSE:ASHOKLEY-EQ",
    "NSE:UNOMINDA-EQ","NSE:BAJAJ-AUTO-EQ","NSE:HEROMOTOCO-EQ",

    # FIN
    "NSE:SHRIRAMFIN-EQ","NSE:SBIN-EQ","NSE:BSE-EQ","NSE:AXISBANK-EQ",
    "NSE:BAJFINANCE-EQ","NSE:PFC-EQ","NSE:LICHSGFIN-EQ","NSE:KOTAKBANK-EQ",
    "NSE:RECLTD-EQ","NSE:BAJAJFINSV-EQ","NSE:JIOFIN-EQ",
    "NSE:HDFCBANK-EQ","NSE:ICICIBANK-EQ","NSE:SBILIFE-EQ","NSE:HDFCLIFE-EQ",

    # FMCG
    "NSE:ITC-EQ","NSE:HINDUNILVR-EQ","NSE:NESTLEIND-EQ","NSE:DABUR-EQ",
    "NSE:BRITANNIA-EQ","NSE:MARICO-EQ","NSE:TATACONSUM-EQ",

    # IT
    "NSE:TCS-EQ","NSE:INFY-EQ","NSE:HCLTECH-EQ","NSE:TECHM-EQ",
    "NSE:LTIM-EQ","NSE:MPHASIS-EQ",

    # METAL
    "NSE:TATASTEEL-EQ","NSE:JSWSTEEL-EQ","NSE:HINDALCO-EQ","NSE:VEDL-EQ",

    # PHARMA
    "NSE:SUNPHARMA-EQ","NSE:DRREDDY-EQ","NSE:CIPLA-EQ","NSE:DIVISLAB-EQ",

    # OIL
    "NSE:RELIANCE-EQ","NSE:ONGC-EQ","NSE:BPCL-EQ","NSE:IOC-EQ"
]

# ------------------------------------------------------------
# STATE BUFFERS
# ------------------------------------------------------------
tick_cache = {}
candle_buf = {}
last_day_vol = {}
bias_done = False

# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------
def now_str():
    return datetime.now().strftime("%H:%M:%S")

def post_webapp(action, payload):
    try:
        requests.post(
            WEBAPP_URL,
            json={"action": action, "payload": payload},
            timeout=3
        )
    except:
        pass

def candle_direction(o, c):
    if c > o: return "GREEN"
    if c < o: return "RED"
    return "NEUTRAL"

# ------------------------------------------------------------
# 5 MIN CANDLE ENGINE
# ------------------------------------------------------------
def handle_tick(symbol, ltp, vol, ts):
    bucket = ts - (ts % CANDLE_SEC)

    if symbol not in candle_buf:
        candle_buf[symbol] = {
            "start": bucket,
            "open": ltp,
            "high": ltp,
            "low": ltp,
            "close": ltp,
            "cum_vol": vol
        }
        last_day_vol[symbol] = vol
        return

    c = candle_buf[symbol]

    if c["start"] == bucket:
        c["high"] = max(c["high"], ltp)
        c["low"]  = min(c["low"], ltp)
        c["close"] = ltp
        c["cum_vol"] = vol
    else:
        # close candle
        vol_diff = max(0, c["cum_vol"] - last_day_vol.get(symbol, 0))
        last_day_vol[symbol] = c["cum_vol"]

        row = {
            "symbol": symbol,
            "time": datetime.fromtimestamp(c["start"]).strftime("%Y-%m-%d %H:%M:%S"),
            "timeframe": "5",
            "open": c["open"],
            "high": c["high"],
            "low": c["low"],
            "close": c["close"],
            "volume": vol_diff,
            "candle_index": 0,
            "lowest_volume_so_far": 0,
            "is_signal": False,
            "direction": candle_direction(c["open"], c["close"])
        }

        post_webapp("pushCandle", {"candles": [row]})

        candle_buf[symbol] = {
            "start": bucket,
            "open": ltp,
            "high": ltp,
            "low": ltp,
            "close": ltp,
            "cum_vol": vol
        }

# ------------------------------------------------------------
# BIAS LOGIC (REAL ADV / DEC)
# ------------------------------------------------------------
def run_bias():
    adv = 0
    dec = 0

    for s, t in tick_cache.items():
        if t["ltp"] >= t["prev"]:
            adv += 1
        else:
            dec += 1

    bias = "NEUTRAL"
    total = adv + dec
    if total > 0:
        if adv / total >= 0.6:
            bias = "BULLISH"
        elif dec / total >= 0.6:
            bias = "BEARISH"

    post_webapp("pushState", {
        "items": [
            {"key": "ADVANCES", "value": adv},
            {"key": "DECLINES", "value": dec},
            {"key": "BIAS", "value": bias}
        ]
    })

# ------------------------------------------------------------
# FYERS WS CALLBACK
# ------------------------------------------------------------
def on_message(msg):
    data = msg
    sym = data.get("symbol")
    ltp = data.get("ltp")
    vol = data.get("vol_traded_today")
    ts  = data.get("exch_feed_time")

    if not sym: return

    prev = tick_cache.get(sym, {}).get("ltp", ltp)
    tick_cache[sym] = {"ltp": ltp, "prev": prev}

    handle_tick(sym, ltp, vol, ts)

def on_open():
    ws.subscribe(symbols=SYMBOLS, data_type="SymbolUpdate")

# ------------------------------------------------------------
# ENGINE LOOP
# ------------------------------------------------------------
def engine_loop():
    global bias_done

    while True:
        t = now_str()

        if t >= BIAS_TIME and not bias_done:
            run_bias()
            bias_done = True

        if t >= STOP_TIME:
            break

        time.sleep(1)

# ------------------------------------------------------------
# START WS
# ------------------------------------------------------------
ws = data_ws.FyersDataSocket(
    access_token=FYERS_ACCESS_TOKEN,
    on_message=on_message,
    on_connect=on_open,
    reconnect=True
)

# ------------------------------------------------------------
# FLASK (KEEP ALIVE)
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"ok": True})

# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
if __name__ == "__main__":
    threading.Thread(target=ws.connect, daemon=True).start()
    threading.Thread(target=engine_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
