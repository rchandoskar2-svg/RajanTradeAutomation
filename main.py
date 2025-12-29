# ============================================================
# RajanTradeAutomation – main.py
# Phase-0 : FYERS LIVE TICK BY TICK + 5 MIN CANDLE
# WS FLOW LOCKED | ONLY SYMBOLS ADDED
# ============================================================

import os
import time
import threading
from flask import Flask, jsonify, request

# ------------------------------------------------------------
# Basic Logs
# ------------------------------------------------------------
print("🚀 main.py STARTED")

# ------------------------------------------------------------
# ENV CHECK
# ------------------------------------------------------------
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

print("🔍 ENV CHECK")
print("FYERS_CLIENT_ID =", FYERS_CLIENT_ID)
print(
    "FYERS_ACCESS_TOKEN prefix =",
    FYERS_ACCESS_TOKEN[:20] if FYERS_ACCESS_TOKEN else "❌ MISSING"
)

if not FYERS_CLIENT_ID or not FYERS_ACCESS_TOKEN:
    raise Exception("❌ FYERS ENV variables missing")

# ------------------------------------------------------------
# Flask App (Ping + Redirects)
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "RajanTradeAutomation"})

@app.route("/callback")
def fyers_callback():
    auth_code = request.args.get("auth_code")
    print("🔑 FYERS CALLBACK HIT | AUTH CODE =", auth_code)
    return jsonify({"status": "callback_received", "auth_code": auth_code})

@app.route("/fyers-redirect")
def fyers_redirect():
    auth_code = request.args.get("auth_code") or request.args.get("code")
    state = request.args.get("state")

    print("🔑 FYERS REDIRECT HIT")
    print("AUTH CODE =", auth_code)
    print("STATE =", state)

    return jsonify({
        "status": "redirect_received",
        "auth_code": auth_code,
        "state": state
    })

# ------------------------------------------------------------
# FYERS WebSocket
# ------------------------------------------------------------
print("📦 Importing fyers_apiv3 WebSocket")
from fyers_apiv3.FyersWebsocket import data_ws
print("✅ data_ws IMPORT SUCCESS")

# ------------------------------------------------------------
# 🔒 5-MIN CANDLE ENGINE (LOCAL, PROVEN)
# ------------------------------------------------------------
CANDLE_INTERVAL = 300  # 5 minutes

candles = {}          # symbol -> running candle
last_candle_vol = {}  # symbol -> last candle cumulative volume

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
    ltp = msg.get("ltp")
    vol = msg.get("vol_traded_today")
    ts = msg.get("exch_feed_time")

    if not symbol or ltp is None or vol is None or ts is None:
        return

    start = candle_start(ts)
    c = candles.get(symbol)

    # NEW CANDLE
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

    # UPDATE RUNNING CANDLE
    c["high"] = max(c["high"], ltp)
    c["low"] = min(c["low"], ltp)
    c["close"] = ltp
    c["cum_vol"] = vol

# ------------------------------------------------------------
# WebSocket Callbacks (WS FLOW UNCHANGED)
# ------------------------------------------------------------
def on_message(message):
    print("📩 WS MESSAGE:", message)
    update_candle_from_tick(message)

def on_error(message):
    print("❌ WS ERROR:", message)

def on_close(message):
    print("🔌 WS CLOSED:", message)

def on_connect():
    print("🔗 WS CONNECTED")

    symbols = [
        "NSE:UNOMINDA-EQ","NSE:TMPV-EQ","NSE:ASHOKLEY-EQ","NSE:BAJAJ-AUTO-EQ",
        "NSE:MARUTI-EQ","NSE:EICHERMOT-EQ","NSE:TVSMOTOR-EQ","NSE:BHARATFORG-EQ",
        "NSE:EXIDEIND-EQ","NSE:BOSCHLTD-EQ","NSE:M&M-EQ","NSE:MOTHERSON-EQ",
        "NSE:SONACOMS-EQ","NSE:HEROMOTOCO-EQ","NSE:TIINDIA-EQ",

        "NSE:SHRIRAMFIN-EQ","NSE:BSE-EQ","NSE:PFC-EQ","NSE:RECLTD-EQ",
        "NSE:ICICIBANK-EQ","NSE:JIOFIN-EQ","NSE:BAJAJFINSV-EQ","NSE:LICHSGFIN-EQ",
        "NSE:AXISBANK-EQ","NSE:HDFCBANK-EQ","NSE:ICICIPRULI-EQ","NSE:SBICARD-EQ",
        "NSE:MUTHOOTFIN-EQ","NSE:BAJFINANCE-EQ","NSE:ICICIGI-EQ","NSE:SBILIFE-EQ",
        "NSE:KOTAKBANK-EQ","NSE:SBIN-EQ","NSE:HDFCLIFE-EQ","NSE:CHOLAFIN-EQ",

        "NSE:VBL-EQ","NSE:RADICO-EQ","NSE:UNITDSPR-EQ","NSE:UBL-EQ",
        "NSE:NESTLEIND-EQ","NSE:EMAMILTD-EQ","NSE:ITC-EQ","NSE:HINDUNILVR-EQ",
        "NSE:DABUR-EQ","NSE:GODREJCP-EQ","NSE:COLPAL-EQ","NSE:BRITANNIA-EQ",
        "NSE:MARICO-EQ","NSE:TATACONSUM-EQ","NSE:PATANJALI-EQ",

        "NSE:PERSISTENT-EQ","NSE:WIPRO-EQ","NSE:INFY-EQ","NSE:TECHM-EQ",
        "NSE:HCLTECH-EQ","NSE:TCS-EQ","NSE:COFORGE-EQ","NSE:OFSS-EQ",
        "NSE:LTIM-EQ","NSE:MPHASIS-EQ",

        "NSE:SUNTV-EQ","NSE:ZEEL-EQ","NSE:NETWORK18-EQ","NSE:HATHWAY-EQ",
        "NSE:PFOCUS-EQ","NSE:NAZARA-EQ","NSE:DBCORP-EQ","NSE:SAREGAMA-EQ",
        "NSE:TIPSMUSIC-EQ","NSE:PVRINOX-EQ",

        "NSE:NATIONALUM-EQ","NSE:LLOYDSME-EQ","NSE:HINDCOPPER-EQ","NSE:WELCORP-EQ",
        "NSE:SAIL-EQ","NSE:NMDC-EQ","NSE:HINDZINC-EQ","NSE:APLAPOLLO-EQ",
        "NSE:JSWSTEEL-EQ","NSE:HINDALCO-EQ","NSE:ADANIENT-EQ","NSE:JINDALSTEL-EQ",
        "NSE:VEDL-EQ","NSE:TATASTEEL-EQ","NSE:JSL-EQ",

        "NSE:PPLPHARMA-EQ","NSE:WOCKPHARMA-EQ","NSE:AJANTPHARM-EQ",
        "NSE:GLENMARK-EQ","NSE:LAURUSLABS-EQ","NSE:SUNPHARMA-EQ","NSE:ALKEM-EQ",
        "NSE:GLAND-EQ","NSE:MANKIND-EQ","NSE:IPCALAB-EQ","NSE:DIVISLAB-EQ",
        "NSE:DRREDDY-EQ","NSE:LUPIN-EQ","NSE:TORNTPHARM-EQ","NSE:BIOCON-EQ",
        "NSE:JBCHEPHARM-EQ","NSE:AUROPHARMA-EQ","NSE:ZYDUSLIFE-EQ",
        "NSE:ABBOTINDIA-EQ","NSE:CIPLA-EQ",

        "NSE:ANANTRAJ-EQ","NSE:SOBHA-EQ","NSE:PHOENIXLTD-EQ","NSE:BRIGADE-EQ",
        "NSE:LODHA-EQ","NSE:DLF-EQ","NSE:OBEROIRLTY-EQ","NSE:SIGNATURE-EQ",
        "NSE:GODREJPROP-EQ","NSE:PRESTIGE-EQ",

        "NSE:GSPL-EQ","NSE:BPCL-EQ","NSE:GAIL-EQ","NSE:HINDPETRO-EQ",
        "NSE:MGL-EQ","NSE:PETRONET-EQ","NSE:CASTROLIND-EQ","NSE:RELIANCE-EQ",
        "NSE:ONGC-EQ","NSE:IGL-EQ","NSE:IOC-EQ","NSE:GUJGASLTD-EQ","NSE:OIL-EQ"
    ]

    print("📡 Subscribing symbols:", len(symbols))

    fyers_ws.subscribe(
        symbols=symbols,
        data_type="SymbolUpdate"
    )

# ------------------------------------------------------------
# Start WebSocket (NON-BLOCKING) – 🔒 UNCHANGED
# ------------------------------------------------------------
def start_ws():
    try:
        print("🧵 WS THREAD STARTED")

        global fyers_ws
        fyers_ws = data_ws.FyersDataSocket(
            access_token=FYERS_ACCESS_TOKEN,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_connect=on_connect,
            reconnect=True
        )

        print("✅ FyersDataSocket CREATED")
        fyers_ws.connect()
        print("📶 WS CONNECT CALLED")

    except Exception as e:
        print("🔥 WS THREAD CRASHED:", e)

ws_thread = threading.Thread(target=start_ws, daemon=True)
ws_thread.start()

# ------------------------------------------------------------
# Start Flask (MAIN THREAD)
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Starting Flask on port {port}")
    app.run(host="0.0.0.0", port=port)
