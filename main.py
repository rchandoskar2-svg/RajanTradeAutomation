# ============================================================
# RajanTradeAutomation – Main Backend (Render / Flask)
# Version: 6.1 (Stable – Bias Window + WS Engine + Crash Safe)
# ============================================================

from flask import Flask, request, jsonify
import requests
import os
import time
import threading
import traceback

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
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

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

# Flask App
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
# 1) Historical Candle Fetch (3 candles)
# ------------------------------------------------------------
def fetch_historical(symbol):
    """Fetch 3 historical candles (9:15-20, 20-25, 25-30)"""
    candles = []
    for i in range(3):
        candles.append({
            "symbol": symbol,
            "time": f"2025-12-05T09:{15 + i*5}:00+05:30",
            "timeframe": "5m",
            "open": 620 + i,
            "high": 623 + i,
            "low": 619 + i,
            "close": 622 + i,
            "volume": 150000 + i * 10000,
            "candle_index": i+1,
            "lowest_volume_so_far": min([150000,160000,170000][: i+1]),
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
        if row.get("selected") is True:
            symbol = row["symbol"]
            candles = fetch_historical(symbol)
            call_webapp("pushCandle", {"candles": candles})

    HIST_DONE = True
    print("📘 Historical fill completed.")

# ------------------------------------------------------------
# 2) Bias Calculation + SectorPerf + StockList
# ------------------------------------------------------------
def compute_bias():
    """Fake NIFTY50 bias calc (replace with actual NSE)"""
    adv = 35
    dec = 10
    bias = "BUY" if adv > dec else "SELL"
    strength = (adv * 100) / (adv + dec)
    return bias, strength


def run_bias_sector_stock():
    global BIAS_DONE
    if BIAS_DONE:
        return None

    bias, strength = compute_bias()
    print("📗 Bias:", bias, "Strength:", strength)

    # Top sectors example
    sectors = [
        {"sector_name": "NIFTY AUTO", "sector_code": "AUTO", "%chg": 1.11, "advances": 15, "declines": 5},
        {"sector_name": "NIFTY METAL", "sector_code": "METAL", "%chg": 1.05, "advances": 10, "declines": 5}
    ]

    call_webapp("updateSectorPerf", {"sectors": sectors})

    # Stocks Example
    stocks = [
        {"symbol": "NSE:SBIN-EQ", "direction_bias": bias, "sector": "NIFTY AUTO",
         "%chg": 1.22, "ltp": 622.4, "volume": 1250000, "selected": True}
    ]

    call_webapp("updateStockList", {"stocks": stocks})

    BIAS_DONE = True
    return stocks

# ------------------------------------------------------------
# 3) WebSocket – Safe Start
# ------------------------------------------------------------
def on_message(msg):
    print("WS Tick:", msg)


def on_error(e):
    print("WS ERROR:", e)


def on_close(e):
    print("WS CLOSED:", e)


def on_open():
    global FYERS_WS, SUBSCRIBED
    if SUBSCRIBED:
        FYERS_WS.subscribe(symbols=list(SUBSCRIBED), data_type="SymbolUpdate")
    FYERS_WS.keep_running()


def start_ws():
    """Start WebSocket only if library is present"""
    global FYERS_WS
    if not FYERS_WS_AVAILABLE:
        print("⚠️ WebSocket skipped (library missing)")
        return

    if not FYERS_ACCESS_TOKEN:
        print("⚠️ WebSocket skipped (missing token)")
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
# 4) LIVE ENGINE (After 09:30)
# ------------------------------------------------------------
def start_live_engine(stocks):
    global LIVE_STARTED
    if LIVE_STARTED:
        return
    LIVE_STARTED = True

    # Subscribe selected symbols
    for row in stocks:
        if row.get("selected"):
            SUBSCRIBED.add(row["symbol"])

    start_ws()
    print("🚀 LIVE engine started with symbols:", SUBSCRIBED)


# ------------------------------------------------------------
# MASTER ENGINE LOOP
# ------------------------------------------------------------
def engine_loop():
    print("🔥 Engine booting… v6.1")
    time.sleep(3)

    while True:
        try:
            t = now_time()

            # 1) Auto start window
            if t == ENGINE_START:
                print("🔧 Auto-start @09:10")
                set_state("ENGINE_STARTUP", "OK")

            # 2) Bias window
            if within(t, BIAS_START, BIAS_END):
                stocks = run_bias_sector_stock()

            # 3) Historical window
            if within(t, HIST_FILL_START, BIAS_START):
                # Fetch stocks from sheet
                sheet = call_webapp("getStockList", {})
                rows = sheet.get("stocks", [])
                run_historical_fill(rows)

            # 4) Live engine start after 09:30
            if t >= "09:30" and not LIVE_STARTED:
                sheet = call_webapp("getStockList", {})
                rows = sheet.get("stocks", [])
                start_live_engine(rows)

        except Exception as e:
            print("❌ ENGINE CRASH:", e)
            traceback.print_exc()

        time.sleep(5)


def start_background():
    th = threading.Thread(target=engine_loop, daemon=True)
    th.start()


start_background()

# ------------------------------------------------------------
# API ROUTES
# ------------------------------------------------------------
@app.route("/")
def root():
    return "RajanTradeAutomation backend v6.1 — LIVE", 200

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
