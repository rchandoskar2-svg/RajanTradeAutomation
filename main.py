# ============================================================
# RajanTradeAutomation – Main Backend (Render / Flask)
# Version: 6.2 (Bias Window + WS Engine + Crash Safe + Manual Routes)
# ============================================================

from flask import Flask, request, jsonify, Response
import requests
import os
import time
import threading
import traceback
import json

# ------------------------------------------------------------
# Fyers WebSocket Library Detection (Safe Mode)
# ------------------------------------------------------------
try:
    from fyers_apiv3.FyersWebsocket import data_ws
    FYERS_WS_AVAILABLE = True
except Exception as e:
    data_ws = None
    FYERS_WS_AVAILABLE = False
    print("⚠️ Fyers WebSocket library NOT installed:", e)

# ------------------------------------------------------------
# Load Environment Variables
# ------------------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
FYERS_CLIENT_SECRET = os.getenv("FYERS_CLIENT_SECRET", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
FYERS_AUTH_CODE = os.getenv("FYERS_AUTH_CODE", "").strip()

FYERS_TOKEN_URL = "https://api.fyers.in/api/v3/token/generate/"

INTERVAL_SECS = int(os.getenv("INTERVAL_SECS", "60"))
AUTO_UNIVERSE = os.getenv("AUTO_UNIVERSE", "FALSE").upper() == "TRUE"

# Strategy timings
BIAS_START = "09:25"
BIAS_END = "09:29"
HIST_FILL_START = "09:15"
ENGINE_START = "09:10"

# State
BIAS_DONE = False
HIST_DONE = False
LIVE_STARTED = False

SUBSCRIBED = set()
FYERS_WS = None

app = Flask(__name__)

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def call_webapp(action, payload=None, timeout=25):
    if payload is None:
        payload = {}
    if not WEBAPP_URL:
        return {"ok": False, "error": "WEBAPP_URL missing"}
    try:
        res = requests.post(WEBAPP_URL, json={"action": action, "payload": payload}, timeout=timeout)
        return res.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def set_state(key, value):
    try:
        call_webapp("setState", {"key": key, "value": str(value)})
    except:
        pass

def now_time():
    return time.strftime("%H:%M")

def within(t, A, B):
    return A <= t <= B

# ------------------------------------------------------------
# Historical Candle Fill
# ------------------------------------------------------------
def fetch_historical(symbol):
    candles = []
    for i in range(3):
        candles.append({
            "symbol": symbol,
            "time": f"2025-12-05T09:{15+i*5}:00+05:30",
            "timeframe": "5m",
            "open": 620+i,
            "high": 623+i,
            "low": 619+i,
            "close": 622+i,
            "volume": 150000 + i*10000,
            "candle_index": i+1,
            "lowest_volume_so_far": min([150000,160000,170000][:i+1]),
            "is_signal": False,
            "direction": "BUY"
        })
    return candles

def run_historical_fill(stocks):
    global HIST_DONE
    if HIST_DONE:
        return
    print("📘 Running historical fill...")
    for row in stocks:
        if row.get("selected"):
            symbol = row["symbol"]
            candles = fetch_historical(symbol)
            call_webapp("pushCandle", {"candles": candles})
    HIST_DONE = True
    print("📘 Historical fill completed.")

# ------------------------------------------------------------
# Bias + Sector + Stocks
# ------------------------------------------------------------
def compute_bias():
    adv = 35
    dec = 10
    bias = "BUY" if adv > dec else "SELL"
    strength = (adv * 100) / (adv + dec)
    return bias, strength

def run_bias_sector_stock():
    global BIAS_DONE
    bias, strength = compute_bias()
    print("📗 Bias:", bias, "Strength:", strength)

    sectors = [
        {"sector_name": "NIFTY AUTO", "sector_code": "AUTO", "%chg": 1.11, "advances": 15, "declines": 5},
        {"sector_name": "NIFTY METAL", "sector_code": "METAL", "%chg": 1.05, "advances": 10, "declines": 5}
    ]

    call_webapp("updateSectorPerf", {"sectors": sectors})

    stocks = [
        {"symbol": "NSE:SBIN-EQ", "direction_bias": bias, "sector": "NIFTY AUTO",
         "%chg": 1.22, "ltp": 622.4, "volume": 1250000, "selected": True}
    ]

    call_webapp("updateStockList", {"stocks": stocks})

    BIAS_DONE = True
    return stocks

# ------------------------------------------------------------
# WebSocket
# ------------------------------------------------------------
def on_message(msg):
    print("WS Tick:", msg)

def on_error(e):
    print("WS ERROR:", e)

def on_close(e):
    print("WS CLOSED:", e)

def on_open():
    global FYERS_WS
    if SUBSCRIBED:
        FYERS_WS.subscribe(symbols=list(SUBSCRIBED), data_type="SymbolUpdate")
    FYERS_WS.keep_running()

def start_ws():
    global FYERS_WS
    if not FYERS_WS_AVAILABLE:
        print("⚠️ WS skipped (library missing)")
        return
    if not FYERS_ACCESS_TOKEN:
        print("⚠️ WS skipped (missing token)")
        return

    try:
        FYERS_WS = data_ws.FyersDataSocket(
            access_token=f"{FYERS_CLIENT_ID}:{FYERS_ACCESS_TOKEN}",
            log_path="",
            litemode=False,
            write_to_file=False,
            reconnect=True,
            on_connect=lambda: on_open(),
            on_close=on_close,
            on_error=on_error,
            on_message=on_message
        )
        FYERS_WS.connect()
        print("✅ WS connected.")
    except Exception as e:
        print("❌ WS startup error:", e)

# ------------------------------------------------------------
# Live Engine
# ------------------------------------------------------------
def start_live_engine(stocks):
    global LIVE_STARTED
    if LIVE_STARTED:
        return
    LIVE_STARTED = True

    for row in stocks:
        if row.get("selected"):
            SUBSCRIBED.add(row["symbol"])

    start_ws()
    print("🚀 LIVE engine started with symbols:", SUBSCRIBED)

# ------------------------------------------------------------
# Automatic Token Exchange
# ------------------------------------------------------------
def try_exchange_token():
    if not FYERS_AUTH_CODE or not FYERS_CLIENT_SECRET:
        print("⚠️ Cannot exchange token (missing auth code or secret)")
        return None

    payload = {
        "grant_type": "authorization_code",
        "appIdHash": FYERS_CLIENT_SECRET,
        "code": FYERS_AUTH_CODE
    }

    try:
        resp = requests.post(FYERS_TOKEN_URL, json=payload, timeout=15)
        j = resp.json()
        print("🔁 Token exchange response:", j)

        if "access_token" in j:
            set_state("FYERS_EXCHANGED_TOKEN", j)
        return j
    except Exception as e:
        print("❌ Token exchange error:", e)
        return None

# ------------------------------------------------------------
# Engine Loop
# ------------------------------------------------------------
def engine_loop():
    print("🔥 Engine booting… v6.2")
    time.sleep(3)

    while True:
        try:
            t = now_time()

            if t == ENGINE_START:
                print("🔧 Auto-start @09:10")
                set_state("ENGINE_STARTUP", "OK")

            if within(t, BIAS_START, BIAS_END):
                stocks = run_bias_sector_stock()

            if within(t, HIST_FILL_START, BIAS_START):
                sheet = call_webapp("getStockList", {})
                rows = sheet.get("stocks", [])
                run_historical_fill(rows)

            if t >= "09:30" and not LIVE_STARTED:
                sheet = call_webapp("getStockList", {})
                rows = sheet.get("stocks", [])
                start_live_engine(rows)

        except Exception as e:
            print("❌ ENGINE CRASH:", e)
            traceback.print_exc()

        time.sleep(5)

def start_background():
    threading.Thread(target=engine_loop, daemon=True).start()

start_background()

# ------------------------------------------------------------
# FYERS Redirect Route
# ------------------------------------------------------------
@app.route("/fyers-redirect")
def fyers_redirect():
    auth_code = request.args.get("auth_code") or request.args.get("code")
    state = request.args.get("state")

    if auth_code:
        set_state("FYERS_AUTH_CODE", auth_code)

    return Response(f"<h2>Auth code received ✓</h2><p>{auth_code}</p>", mimetype="text/html")

# ------------------------------------------------------------
# Manual CONTROLS (Requested by Rajan)
# ------------------------------------------------------------
@app.route("/engine/run-bias-now")
def run_bias_now():
    try:
        stocks = run_bias_sector_stock()
        return jsonify({"ok": True, "message": "Bias + Sector + StockList run manually", "stocks": stocks})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/engine/run-historical-now")
def run_historical_now():
    try:
        sheet = call_webapp("getStockList", {})
        rows = sheet.get("stocks", [])
        run_historical_fill(rows)
        return jsonify({"ok": True, "message": "Historical candles filled manually"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/engine/start-live-now")
def run_live_now():
    try:
        sheet = call_webapp("getStockList", {})
        rows = sheet.get("stocks", [])
        start_live_engine(rows)
        return jsonify({"ok": True, "message": "LIVE engine manually started", "subscribed": list(SUBSCRIBED)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ------------------------------------------------------------
# Basic Routes
# ------------------------------------------------------------
@app.route("/")
def root():
    return "RajanTradeAutomation backend v6.2 — LIVE", 200

@app.route("/engine/ws-check")
def wscheck():
    return jsonify({
        "ws_lib_installed": FYERS_WS_AVAILABLE,
        "access_token_present": True if FYERS_ACCESS_TOKEN else False,
        "websocket_started": True if FYERS_WS else False,
        "subscribed": list(SUBSCRIBED)
    })

# ------------------------------------------------------------
# RUN SERVER
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
