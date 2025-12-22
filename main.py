# ============================================================
# RajanTradeAutomation – main.py (Render Stable WS Version)
# FIXED: setuptools<81, FYERS WS, Render-safe threading
# + FYERS CALLBACK URI ROUTE
# + LOCAL-PROVEN 5-MIN CANDLE BUILD (CUM VOL BASED)
# + FYERS-REDIRECT ROUTE (ADDED)
# + GOOGLE SHEET PUSH CANDLE (ADDED)
# ============================================================

import os
import time
import threading
from datetime import datetime
from flask import Flask, jsonify, request
import requests   # ⭐ Needed for push

print("🚀 main.py STARTED")

# ------------------------------------------------------------
# ENV CHECK
# ------------------------------------------------------------
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

print("🔍 ENV CHECK")
print("FYERS_CLIENT_ID =", FYERS_CLIENT_ID)
print("FYERS_ACCESS_TOKEN prefix =", FYERS_ACCESS_TOKEN[:20] if FYERS_ACCESS_TOKEN else "❌ MISSING")

if not FYERS_CLIENT_ID or not FYERS_ACCESS_TOKEN:
    raise Exception("❌ FYERS ENV variables missing")

# ------------------------------------------------------------
# Google Sheet WebApp URL  ⭐ (ADDED YOUR EXEC)
# ------------------------------------------------------------
WEBAPP_URL = "https://script.google.com/macros/s/AKfycbwSDiqsEQW5BI8RuPScSq3VUmPxG7KlFGeDWk5_VK8LqTBe3hMgehJEgCK7Uu1xkE0-/exec"


# ------------------------------------------------------------
# Flask App Base
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "RajanTradeAutomation"})

# ------------------------------------------------------------
# FYERS CALLBACK (Original)
# ------------------------------------------------------------
@app.route("/callback")
def fyers_callback():
    auth_code = request.args.get("auth_code")
    print("🔑 FYERS CALLBACK HIT:", auth_code)
    if not auth_code:
        return jsonify({"error": "auth_code missing"}), 400
    return jsonify({"status": "callback_received", "auth_code": auth_code})

# ------------------------------------------------------------
# FYERS REDIRECT (Custom)
# ------------------------------------------------------------
@app.route("/fyers-redirect")
def fyers_redirect():
    try:
        auth_code = request.args.get("auth_code")
        print("🔑 FYERS REDIRECT HIT:", auth_code)
        if not auth_code:
            return jsonify({"error": "auth_code missing"}), 400
        return jsonify({"status": "redirect_received", "auth_code": auth_code})
    except Exception as e:
        print("🔥 Redirect error:", e)
        return jsonify({"error": str(e)}), 500


# ------------------------------------------------------------
# FYERS WebSocket
# ------------------------------------------------------------
from fyers_apiv3.FyersWebsocket import data_ws
print("✅ data_ws IMPORT SUCCESS")

# ------------------------------------------------------------
# Push Candle to Google Sheet  ⭐⭐⭐
# ------------------------------------------------------------
def push_to_webapp(symbol, c, candle_volume):
    try:
        payload = {
            "action": "pushCandle",
            "payload": {
                "candles": [{
                    "symbol": symbol,
                    "time": c["start"],
                    "timeframe": "5",
                    "open": c["open"],
                    "high": c["high"],
                    "low": c["low"],
                    "close": c["close"],
                    "volume": candle_volume
                }]
            }
        }
        r = requests.post(WEBAPP_URL, json=payload, timeout=4)
        print("📤 PUSH → WebApp:", r.text)
    except Exception as e:
        print("🔥 PUSH ERROR:", e)


# ------------------------------------------------------------
# 5-MIN CANDLE ENGINE
# ------------------------------------------------------------
CANDLE_INTERVAL = 300

candles = {}
last_candle_vol = {}

def get_candle_start(ts):
    return ts - (ts % CANDLE_INTERVAL)

def close_candle(symbol, c):
    prev_vol = last_candle_vol.get(symbol, c["cum_vol"])
    candle_volume = c["cum_vol"] - prev_vol
    last_candle_vol[symbol] = c["cum_vol"]

    # ⭐⭐⭐ PUSH TO GOOGLE SHEET
    push_to_webapp(symbol, c, candle_volume)

    print(f"\n🟩 5m CANDLE {symbol}")
    print(f"Time: {time.strftime('%H:%M:%S', time.localtime(c['start']))}")
    print(f"O:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']} V:{candle_volume}")
    print("---------------------------")

def update_candle_from_tick(msg):
    if not isinstance(msg, dict):
        return

    symbol = msg.get("symbol")
    ltp = msg.get("ltp")
    vol = msg.get("vol_traded_today")
    ts = msg.get("exch_feed_time")

    if not symbol or ltp is None or vol is None or ts is None:
        return

    candle_start = get_candle_start(ts)
    c = candles.get(symbol)

    if c is None or c["start"] != candle_start:
        if c:
            close_candle(symbol, c)

        candles[symbol] = {
            "start": candle_start,
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


# ------------------------------------------------------------
# WebSocket Callbacks
# ------------------------------------------------------------
def on_message(message):
    print("📩 WS:", message)
    try:
        update_candle_from_tick(message)
    except Exception as e:
        print("🔥 Candle logic error:", e)

def on_error(message):
    print("❌ WS ERROR:", message)

def on_close(message):
    print("🔌 WS CLOSED:", message)

def on_connect():
    print("🔗 WS CONNECTED")

    # --------------------------------------------------------
    # ⭐ ALL 160–170 SYMBOLS EXACTLY AS YOU PROVIDED
    # --------------------------------------------------------
    symbols = [
        "NSE:EICHERMOT-EQ","NSE:SONACOMS-EQ","NSE:TVSMOTOR-EQ","NSE:MARUTI-EQ",
        "NSE:TMPV-EQ","NSE:M&M-EQ","NSE:MOTHERSON-EQ","NSE:TIINDIA-EQ",
        "NSE:BHARATFORG-EQ","NSE:BOSCHLTD-EQ","NSE:EXIDEIND-EQ","NSE:ASHOKLEY-EQ",
        "NSE:UNOMINDA-EQ","NSE:BAJAJ-AUTO-EQ","NSE:HEROMOTOCO-EQ",

        "NSE:SHRIRAMFIN-EQ","NSE:SBIN-EQ","NSE:BSE-EQ","NSE:AXISBANK-EQ",
        "NSE:BAJFINANCE-EQ","NSE:PFC-EQ","NSE:LICHSGFIN-EQ","NSE:KOTAKBANK-EQ",
        "NSE:RECLTD-EQ","NSE:BAJAJFINSV-EQ","NSE:ICICIGI-EQ","NSE:JIOFIN-EQ",
        "NSE:HDFCBANK-EQ","NSE:ICICIBANK-EQ","NSE:ICICIPRULI-EQ",
        "NSE:SBILIFE-EQ","NSE:HDFCLIFE-EQ","NSE:SBICARD-EQ",
        "NSE:MUTHOOTFIN-EQ","NSE:CHOLAFIN-EQ",

        "NSE:TATACONSUM-EQ","NSE:PATANJALI-EQ","NSE:BRITANNIA-EQ",
        "NSE:HINDUNILVR-EQ","NSE:GODREJCP-EQ","NSE:MARICO-EQ","NSE:ITC-EQ",
        "NSE:NESTLEIND-EQ","NSE:UBL-EQ","NSE:DABUR-EQ","NSE:EMAMILTD-EQ",
        "NSE:VBL-EQ","NSE:UNITDSPR-EQ","NSE:RADICO-EQ","NSE:COLPAL-EQ",

        "NSE:WIPRO-EQ","NSE:INFY-EQ","NSE:TCS-EQ","NSE:PERSISTENT-EQ",
        "NSE:LTIM-EQ","NSE:MPHASIS-E-EQ","NSE:HCLTECH-EQ","NSE:TECHM-EQ",
        "NSE:COFORGE-EQ","NSE:OFSS-EQ",

        "NSE:ZEEL-EQ","NSE:PVRINOX-EQ","NSE:DBCORP-EQ","NSE:HATHWAY-EQ",
        "NSE:SUNTV-EQ","NSE:TIPSMUSIC-EQ","NSE:NETWORK18-EQ","NSE:PFOCUS-EQ",
        "NSE:NAZARA-EQ","NSE:SAREGAMA-EQ",

        "NSE:APLAPOLLO-EQ","NSE:HINDZINC-EQ","NSE:HINDALCO-EQ","NSE:NATIONALUM-EQ",
        "NSE:TATASTEEL-EQ","NSE:SAIL-EQ","NSE:NMDC-EQ","NSE:LLOYDSME-EQ",
        "NSE:VEDL-EQ","NSE:HINDCOPPER-EQ","NSE:JSWSTEEL-EQ","NSE:ADANIENT-EQ",
        "NSE:JINDALSTEL-EQ","NSE:WELCORP-EQ","NSE:JSL-EQ",

        "NSE:AUROPHARMA-EQ","NSE:LUPIN-EQ","NSE:JBCHEPHARM-EQ","NSE:BIOCON-EQ",
        "NSE:LAURUSLABS-EQ","NSE:ZYDUSLIFE-EQ","NSE:SUNPHARMA-EQ",
        "NSE:MANKIND-EQ","NSE:WOCKPHARMA-EQ","NSE:TORNTPHARM-EQ",
        "NSE:CIPLA-EQ","NSE:AJANTPHARM-EQ","NSE:DRREDDY-EQ","NSE:GLAND-EQ",
        "NSE:ABBOTINDIA-EQ","NSE:ALKEM-EQ","NSE:PPLPHARMA-EQ",
        "NSE:DIVISLAB-EQ","NSE:GLENMARK-EQ","NSE:IPCALAB-EQ",

        "NSE:CANBK-EQ","NSE:BANKINDIA-EQ","NSE:PNB-EQ","NSE:BANKBARODA-EQ",
        "NSE:INDIANB-EQ","NSE:MAHABANK-EQ","NSE:UNIONBANK-EQ","NSE:PSB-EQ",
        "NSE:UCOBANK-EQ","NSE:CENTRALBK-EQ","NSE:IOB-EQ",
        "NSE:IDFCFIRSTB-EQ","NSE:FEDERALBNK-EQ","NSE:YESBANK-EQ",
        "NSE:INDUSINDBK-EQ","NSE:BANDHANBNK-EQ","NSE:RBLBANK-EQ",

        "NSE:IGL-EQ","NSE:PETRONET-EQ","NSE:MGL-EQ","NSE:GAIL-EQ","NSE:IOC-EQ",
        "NSE:RELIANCE-EQ","NSE:ONGC-EQ","NSE:CASTROLIND-EQ","NSE:GUJGASLTD-EQ",
        "NSE:BPCL-EQ","NSE:HINDPETRO-EQ","NSE:GSPL-EQ","NSE:ATGL-EQ",
        "NSE:OIL-EQ","NSE:AEGISLOG-EQ",

        "NSE:SWANCORP-EQ","NSE:ATUL-EQ","NSE:SRF-EQ","NSE:DEEPAKNTR-EQ",
        "NSE:LINDEINDIA-EQ","NSE:FLUOROCHEM-EQ","NSE:PCBL-EQ","NSE:UPL-EQ",
        "NSE:TATACHEM-EQ","NSE:DEEPAKFERT-EQ","NSE:HSCL-EQ","NSE:BAYERCROP-EQ",
        "NSE:SOLARINDS-EQ","NSE:CHAMBLFERT-EQ","NSE:PIDILITIND-EQ",
        "NSE:SUMICHEM-EQ","NSE:PIIND-EQ","NSE:AARTIIND-EQ",
        "NSE:NAVINFLUOR-EQ","NSE:COROMANDEL-EQ"
    ]

    print(f"📡 Subscribing TOTAL symbols: {len(symbols)}")
    fyers_ws.subscribe(symbols=symbols, data_type="SymbolUpdate")

# ------------------------------------------------------------
# Start WS
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

# ------------------------------------------------------------
# Start Flask
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Starting Flask on port {port}")
    app.run(host="0.0.0.0", port=port)
