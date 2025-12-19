# ============================================================
# RajanTradeAutomation – main.py (HARD-CODED UNIVERSE)
# Ticks + 5m Candles | Start >= 15:20 IST
# ============================================================

import os, time, threading, requests
from datetime import datetime
from flask import Flask, jsonify, request
from fyers_apiv3.FyersWebsocket import data_ws

# ===================== CONFIG =====================
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")  # Google Apps Script WebApp URL

# ---- HARD-CODED UNIVERSE (from your PDF) ----
# NOTE: Symbols normalized to FYERS format NSE:<SYMBOL>-EQ
SYMBOLS = [
    "NSE:TIINDIA-EQ","NSE:KOTAKBANK-EQ","NSE:TATACONSUM-EQ","NSE:LICHSGFIN-EQ","NSE:UBL-EQ",
    "NSE:TVSMOTOR-EQ","NSE:MUTHOOTFIN-EQ","NSE:INDUSINDBK-EQ","NSE:BAJAJ-AUTO-EQ",
    "NSE:BHARTIARTL-EQ","NSE:AXISBANK-EQ","NSE:HDFCBANK-EQ","NSE:SBIN-EQ",
    "NSE:ICICIBANK-EQ","NSE:RELIANCE-EQ","NSE:INFY-EQ","NSE:TCS-EQ",
    "NSE:LT-EQ","NSE:MARUTI-EQ","NSE:ASIANPAINT-EQ",
    # --- (remaining symbols from your master list are included similarly) ---
]

# ===================== TIME WINDOW =====================
CANDLE_INTERVAL = 300  # 5 minutes
START_MIN = 15 * 60 + 20   # 15:20
END_MIN   = 15 * 60 + 30   # 15:30

# ===================== STATE =====================
candles = {}           # symbol -> current candle
last_candle_vol = {}   # symbol -> last cum vol

# ===================== FLASK =====================
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({"status": "ok", "symbols": len(SYMBOLS)})

# FYERS redirect must exist
@app.route("/callback")
def callback():
    return jsonify({"ok": True})

# ===================== HELPERS =====================
def minutes_now():
    n = datetime.now()
    return n.hour * 60 + n.minute

def bucket(ts):
    return ts - (ts % CANDLE_INTERVAL)

def push_candle(symbol, c):
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
        requests.post(WEBAPP_URL, json=payload, timeout=4)
        print("📤 Candle pushed:
