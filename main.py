# ============================================================
# RajanTradeAutomation – LIVE WS TEST (STABLE – RENDER SAFE)
# Strategy start: 11:15
# Purpose: Verify FYERS Live Data + 5-min Candles
# ============================================================

from flask import Flask
import os
import time
import threading
from datetime import datetime
import requests

from fyers_apiv3.FyersWebsocket import data_ws

# ------------------------------------------------------------
# ENV
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

if not FYERS_ACCESS_TOKEN:
    raise Exception("FYERS_ACCESS_TOKEN missing in environment")

# ------------------------------------------------------------
# FLASK (Ping / Health)
app = Flask(__name__)

@app.route("/", methods=["GET"])
def root():
    return "LIVE WS TEST RUNNING ⭐", 200

@app.route("/ping", methods=["GET"])
def ping():
    return "PONG", 200

# ------------------------------------------------------------
# CONFIG
CANDLE_INTERVAL = 300  # 5 minutes
STRATEGY_START_HHMM = "11:15"  # 🔥 UPDATED AS REQUESTED

SYMBOLS = [
    "NSE:SBIN-EQ",
    "NSE:VEDL-EQ",
    "NSE:RELIANCE-EQ",
    "NSE:AXISBANK-EQ",
    "NSE:KOTAKBANK-EQ",
]

# ------------------------------------------------------------
# STATE
candles = {}      # symbol -> current candle
last_vtt = {}     # symbol -> last cumulative volume
lock = threading.Lock()

# ------------------------------------------------------------
def now_hhmm():
    return datetime.now().strftime("%H:%M")

def get_candle_start(ts):
    return ts - (ts % CANDLE_INTERVAL)

# ------------------------------------------------------------
def push_candle(symbol, c):
    if not WEBAPP_URL:
        return
    payload = {
        "action": "pushCandle",
        "symbol": symbol,
        "open": c["open"],
        "high": c["high"],
        "low": c["low"],
        "close": c["close"],
        "volume": c["volume"],
        "epoch": c["start"],
        "timeframe": "5m"
    }
    try:
        requests.post(WEBAPP_URL, json=payload, timeout=10)
    except Exception as e:
        print("pushCandle error:", e)

# ------------------------------------------------------------
def onmessage(msg):
    if not isinstance(msg, dict):
        return

    symbol = msg.get("symbol")
    ltp = msg.get("ltp")
    vtt = msg.get("vol_traded_today")
    ts = msg.get("exch_feed_time")

    if symbol not in SYMBOLS:
        return
    if ltp is None or vtt is None or ts is None:
        return
    if now_hhmm() < STRATEGY_START_HHMM:
        return

    with lock:
        prev_vtt = last_vtt.get(symbol, vtt)
        vol = max(vtt - prev_vtt, 0)
        last_vtt[symbol] = vtt

        cstart = get_candle_start(ts)
        c = candles.get(symbol)

        if c is None or c["start"] != cstart:
            if c:
                push_candle(symbol, c)
            candles[symbol] = {
                "start": cstart,
                "open": ltp,
                "high": ltp,
                "low": ltp,
                "close": ltp,
                "volume": vol
            }
        else:
            c["high"] = max(c["high"], ltp)
            c["low"] = min(c["low"], ltp)
            c["close"] = ltp
            c["volume"] += vol

# ------------------------------------------------------------
def onopen():
    print("✅ FYERS WS CONNECTED")
    print("📡 Subscribed symbols:", SYMBOLS)

def onerror(e):
    print("❌ WS ERROR:", e)

def onclose():
    print("⚠️ WS CLOSED")

# ------------------------------------------------------------
def start_ws():
    ws = data_ws.FyersDataSocket(
        access_token=FYERS_ACCESS_TOKEN,
        log_path="",
        litemode=False,
        write_to_file=False,
        reconnect=True,
        on_connect=onopen,
        on_message=onmessage,
        on_error=onerror,
        on_close=onclose
    )
    ws.subscribe(symbols=SYMBOLS, data_type="SymbolUpdate")
    ws.keep_running()

# ------------------------------------------------------------
if __name__ == "__main__":
    # 🔥 IMPORTANT: WS runs as NON-DAEMON thread (Render safe)
    ws_thread = threading.Thread(target=start_ws)
    ws_thread.start()

    # Flask runs in main thread
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
