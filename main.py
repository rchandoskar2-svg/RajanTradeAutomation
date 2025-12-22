# ============================================================
# RajanTradeAutomation – main.py (FINAL – CORRECTED)
# Tick → 5m Candle → Sector Mapping → Signal Engine
# ============================================================

import os
import time
import threading
import requests
from datetime import datetime
from flask import Flask, jsonify
from fyers_apiv3.FyersWebsocket import data_ws

# ============================================================
# ENV (Render) – DO NOT TOUCH
# ============================================================
WEBAPP_URL = os.getenv("WEBAPP_URL")
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

if not WEBAPP_URL or not FYERS_ACCESS_TOKEN:
    raise Exception("Missing ENV variables")

# ============================================================
# TIME CONFIG (LOCKED – STRATEGY)
# ============================================================
TICK_START = "09:14:00"     # silent tick window
BIAS_TIME  = "09:25:05"     # sector snapshot
STOP_TIME  = "15:30:00"     # hard stop
CANDLE_SEC = 300            # 5-minute candles

# ============================================================
# IMPORT STRATEGY MODULES (ALREADY PROVIDED)
# ============================================================
from sector_mapping import SECTOR_MAP
from sector_engine import maybe_run_sector_decision, get_bias
from signal_engine import on_new_candle

# ============================================================
# SYMBOL LIST (FULL – DO NOT TRIM)
# ============================================================
SYMBOLS = [
    "NSE:EICHERMOT-EQ","NSE:SONACOMS-EQ","NSE:TVSMOTOR-EQ","NSE:MARUTI-EQ",
    "NSE:TMPV-EQ","NSE:M&M-EQ","NSE:MOTHERSON-EQ","NSE:TIINDIA-EQ",
    "NSE:BHARATFORG-EQ","NSE:BOSCHLTD-EQ","NSE:EXIDEIND-EQ","NSE:ASHOKLEY-EQ",
    "NSE:UNOMINDA-EQ","NSE:BAJAJ-AUTO-EQ","NSE:HEROMOTOCO-EQ",

    "NSE:SHRIRAMFIN-EQ","NSE:SBIN-EQ","NSE:BSE-EQ","NSE:AXISBANK-EQ",
    "NSE:BAJFINANCE-EQ","NSE:PFC-EQ","NSE:LICHSGFIN-EQ","NSE:KOTAKBANK-EQ",
    "NSE:RECLTD-EQ","NSE:BAJAJFINSV-EQ","NSE:JIOFIN-EQ",
    "NSE:HDFCBANK-EQ","NSE:ICICIBANK-EQ","NSE:SBILIFE-EQ","NSE:HDFCLIFE-EQ",

    "NSE:ITC-EQ","NSE:HINDUNILVR-EQ","NSE:NESTLEIND-EQ","NSE:DABUR-EQ",
    "NSE:BRITANNIA-EQ","NSE:MARICO-EQ","NSE:TATACONSUM-EQ",

    "NSE:TCS-EQ","NSE:INFY-EQ","NSE:HCLTECH-EQ","NSE:TECHM-EQ",
    "NSE:LTIM-EQ","NSE:MPHASIS-EQ",

    "NSE:TATASTEEL-EQ","NSE:JSWSTEEL-EQ","NSE:HINDALCO-EQ","NSE:VEDL-EQ",

    "NSE:SUNPHARMA-EQ","NSE:DRREDDY-EQ","NSE:CIPLA-EQ","NSE:DIVISLAB-EQ",

    "NSE:RELIANCE-EQ","NSE:ONGC-EQ","NSE:BPCL-EQ","NSE:IOC-EQ"
]

# ============================================================
# GLOBAL STATE
# ============================================================
tick_cache = {}
candle_buf = {}
prev_cum_vol = {}
candle_index = {}

day_open_price = {}
pct_change_map = {}

SELECTED_STOCKS = set()

SETTINGS = {
    "THRESHOLD": 80,
    "MAX_UP": 2.5,
    "MAX_DN": 2.5,
    "BUY_SECTORS": 2,
    "SELL_SECTORS": 2,
    "PER_TRADE_RISK": 500
}

# ============================================================
# HELPERS
# ============================================================
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

# ============================================================
# PHASE-B ACTIVATION
# ============================================================
def activate_phase_b(symbols):
    global SELECTED_STOCKS
    SELECTED_STOCKS = set(symbols)
    print("PHASE-B ACTIVE | SELECTED STOCKS:", len(SELECTED_STOCKS))

# ============================================================
# 5-MIN CANDLE ENGINE (CORRECT VOLUME LOGIC)
# ============================================================
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
        prev_cum_vol[symbol] = vol
        candle_index[symbol] = 0
        return

    c = candle_buf[symbol]

    if c["start"] == bucket:
        c["high"] = max(c["high"], ltp)
        c["low"]  = min(c["low"], ltp)
        c["close"] = ltp
        c["cum_vol"] = vol
    else:
        candle_index[symbol] += 1

        vol_diff = max(0, c["cum_vol"] - prev_cum_vol.get(symbol, c["cum_vol"]))
        prev_cum_vol[symbol] = c["cum_vol"]

        candle = {
            "symbol": symbol,
            "time": datetime.fromtimestamp(c["start"]).strftime("%Y-%m-%d %H:%M:%S"),
            "timeframe": "5",
            "open": c["open"],
            "high": c["high"],
            "low": c["low"],
            "close": c["close"],
            "volume": vol_diff,
            "index": candle_index[symbol],
            "direction": candle_direction(c["open"], c["close"])
        }

        post_webapp("pushCandle", {"candles": [candle]})

        if symbol in SELECTED_STOCKS:
            bias = get_bias(symbol)
            signal = on_new_candle(symbol, candle, bias, SETTINGS)
            if signal:
                post_webapp("pushSignal", {"signals": [signal]})

        candle_buf[symbol] = {
            "start": bucket,
            "open": ltp,
            "high": ltp,
            "low": ltp,
            "close": ltp,
            "cum_vol": vol
        }

# ============================================================
# FYERS WS CALLBACK
# ============================================================
def on_message(msg):
    sym = msg.get("symbol")
    ltp = msg.get("ltp")
    vol = msg.get("vol_traded_today")
    ts  = msg.get("exch_feed_time")

    if not sym:
        return

    if sym not in day_open_price:
        day_open_price[sym] = ltp

    pct_change_map[sym] = ((ltp - day_open_price[sym]) / day_open_price[sym]) * 100

    tick_cache[sym] = {"ltp": ltp}

    handle_tick(sym, ltp, vol, ts)

def on_open():
    ws.subscribe(symbols=SYMBOLS, data_type="SymbolUpdate")

# ============================================================
# ENGINE LOOP
# ============================================================
def engine_loop():
    while True:
        now = datetime.now()

        maybe_run_sector_decision(
            now=now,
            pct_change_map=pct_change_map,
            bias_time=BIAS_TIME,
            threshold=SETTINGS["THRESHOLD"],
            max_up=SETTINGS["MAX_UP"],
            max_dn=SETTINGS["MAX_DN"],
            buy_sector_count=SETTINGS["BUY_SECTORS"],
            sell_sector_count=SETTINGS["SELL_SECTORS"],
            sector_map=SECTOR_MAP,
            phase_b_switch=activate_phase_b
        )

        if now.strftime("%H:%M:%S") >= STOP_TIME:
            break

        time.sleep(1)

# ============================================================
# START WS
# ============================================================
ws = data_ws.FyersDataSocket(
    access_token=FYERS_ACCESS_TOKEN,
    on_message=on_message,
    on_connect=on_open,
    reconnect=True
)

# ============================================================
# FLASK KEEP-ALIVE (LOCKED)
# ============================================================
app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"ok": True})

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    threading.Thread(target=ws.connect, daemon=True).start()
    threading.Thread(target=engine_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
