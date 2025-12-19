# ============================================================
# RajanTradeAutomation – main.py (UNIVERSE DRIVEN)
# FYERS Live Ticks → 5m Candles → Google Sheets
# Start Time: 09:15 IST
# ============================================================

import os
import time
import threading
import requests
from datetime import datetime
from flask import Flask, jsonify
from fyers_apiv3.FyersWebsocket import data_ws

# ===================== CONFIG =====================
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")   # Google Apps Script WebApp URL

CANDLE_INTERVAL = 300  # 5 minutes
START_MIN = 9 * 60 + 15
END_MIN   = 15 * 60 + 30

# ===================== STATE =====================
candles = {}            # symbol -> current candle
last_candle_vol = {}    # symbol -> last cumulative volume
SYMBOLS = []

# ===================== FLASK =====================
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({
        "status": "ok",
        "symbols": len(SYMBOLS)
    })

@app.route("/callback")
def callback():
    return jsonify({"ok": True})

# ===================== HELPERS =====================
def minutes_now():
    n = datetime.now()
    return n.hour * 60 + n.minute

def bucket(ts):
    return ts - (ts % CANDLE_INTERVAL)

# ===================== UNIVERSE LOADER =====================
def load_universe():
    try:
        payload = {"action": "getUniverse"}
        r = requests.post(WEBAPP_URL, json=payload, timeout=15)
        data = r.json()
        syms = data.get("symbols", [])
        print(f"✅ Universe loaded: {len(syms)} symbols")
        return syms
    except Exception as e:
        print("❌ Universe load failed:", e)
        return []

# ===================== PUSH CANDLE =====================
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
        print(f"📤 Candle pushed {symbol} @ {payload['payload']['candles'][0]['time']}")
    except Exception as e:
        print("❌ Candle push failed:", e)

# ===================== WS CALLBACKS =====================
def onmessage(msg):
    if "symbol" not in msg or "ltp" not in msg:
        return

    symbol = msg["symbol"]
    ltp = msg["ltp"]
    ts = int(msg.get("timestamp", time.time()))
    cum_vol = msg.get("vol_traded_today", 0)

    now_min = minutes_now()
    if now_min < START_MIN or now_min > END_MIN:
        return

    start = bucket(ts)
    c = candles.get(symbol)

    if not c or c["start"] != start:
        if c:
            push_candle(symbol, c)

        candles[symbol] = {
            "start": start,
            "open": ltp,
            "high": ltp,
            "low": ltp,
            "close": ltp,
            "cum_vol": cum_vol
        }
    else:
        c["high"] = max(c["high"], ltp)
        c["low"] = min(c["low"], ltp)
        c["close"] = ltp
        c["cum_vol"] = cum_vol

def onerror(err):
    print("WS ERROR:", err)

def onclose(msg):
    print("WS CLOSED:", msg)

def onopen():
    print("✅ WS OPEN – subscribing universe")
    ws.subscribe(symbols=SYMBOLS, data_type="SymbolUpdate")

# ===================== WS START =====================
def start_ws():
    global ws
    ws = data_ws.FyersWebsocket(
        access_token=FYERS_ACCESS_TOKEN,
        onmessage=onmessage,
        onerror=onerror,
        onclose=onclose,
        reconnect=True
    )
    ws.connect()
    ws.keep_running()

# ===================== MAIN =====================
if __name__ == "__main__":
    SYMBOLS.extend(load_universe())

    if not SYMBOLS:
        raise RuntimeError("Universe empty – aborting startup")

    threading.Thread(target=start_ws, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
