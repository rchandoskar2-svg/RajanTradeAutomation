# ============================================================
# RajanTradeAutomation – FINAL main.py
# BASE: Your LOCKED Flask Backend (redirect + ping + tests)
# ADDITIONS:
#   - FYERS WebSocket live ticks
#   - Settings-sheet driven timings
#   - Tick → 5m Candle Engine
#   - Sector breadth (80%) selection
#   - Signal engine integration
# ============================================================

from flask import Flask, request, jsonify
import requests
import os
import time
import threading
from datetime import datetime
from fyers_apiv3.FyersWebsocket import data_ws

# ============================================================
# FLASK APP (LOCKED BASE)
# ============================================================
app = Flask(__name__)

# ============================================================
# ENVIRONMENT VARIABLES (Render)
# ============================================================
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY", "").strip()
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

# ============================================================
# IMPORT STRATEGY MODULES (ALREADY PROVIDED BY YOU)
# ============================================================
from sector_mapping import SECTOR_MAP
from sector_engine import maybe_run_sector_decision, get_bias
from signal_engine import on_new_candle

# ============================================================
# GLOBAL STATE
# ============================================================
CANDLE_SEC = 300  # 5 min

tick_cache = {}
candle_buf = {}
prev_cum_vol = {}
candle_index = {}

day_open_price = {}
pct_change_map = {}

SELECTED_STOCKS = set()
SETTINGS = {}
TICK_START_TS = 0

# ============================================================
# HELPERS
# ============================================================
def call_webapp(action, payload=None, timeout=15):
    if payload is None:
        payload = {}
    body = {"action": action, "payload": payload}
    try:
        r = requests.post(WEBAPP_URL, json=body, timeout=timeout)
        try:
            return r.json()
        except Exception:
            return {"ok": True, "raw": r.text}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def read_settings():
    res = call_webapp("getSettings", {})
    return res.get("settings", {})

def candle_direction(o, c):
    if c > o:
        return "GREEN"
    if c < o:
        return "RED"
    return "DOJI"

# ============================================================
# ROOT + HEALTH CHECK (LOCKED)
# ============================================================
@app.route("/", methods=["GET"])
def root():
    return "RajanTradeAutomation backend is LIVE ✅", 200

@app.route("/ping", methods=["GET"])
def ping():
    return "PONG", 200

# ============================================================
# SETTINGS FETCH (LOCKED)
# ============================================================
@app.route("/getSettings", methods=["GET"])
def get_settings():
    result = call_webapp("getSettings", {})
    return jsonify(result)

# ============================================================
# FYERS OAUTH REDIRECT (LOCKED)
# ============================================================
@app.route("/fyers-redirect", methods=["GET"])
def fyers_redirect():
    status = request.args.get("s") or request.args.get("status", "")
    auth_code = request.args.get("auth_code", "")
    state = request.args.get("state", "")

    html = f"""
    <h2>Fyers Redirect Handler</h2>
    <p>Status: <b>{status}</b></p>
    <p>State: <b>{state}</b></p>
    <p><b>Auth Code (copy & save safely):</b></p>
    <textarea rows="5" cols="120">{auth_code}</textarea>
    <p>हा code कुणालाही share करू नकोस.</p>
    """
    return html, 200

# ============================================================
# 5-MIN CANDLE ENGINE
# ============================================================
def handle_tick(symbol, ltp, vol, ts):
    global candle_buf, prev_cum_vol, candle_index

    if ts < TICK_START_TS:
        return

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
        c["low"] = min(c["low"], ltp)
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
            "candle_index": candle_index[symbol],
            "lowest_volume_so_far": 0,
            "is_signal": False,
            "direction": candle_direction(c["open"], c["close"])
        }

        call_webapp("pushCandle", {"candles": [candle]})

        if symbol in SELECTED_STOCKS:
            bias = get_bias(symbol)
            signal = on_new_candle(symbol, candle, bias, SETTINGS)
            if signal:
                call_webapp("pushSignal", {"signals": [signal]})

        candle_buf[symbol] = {
            "start": bucket,
            "open": ltp,
            "high": ltp,
            "low": ltp,
            "close": ltp,
            "cum_vol": vol
        }

# ============================================================
# FYERS WS CALLBACKS
# ============================================================
def on_message(msg):
    sym = msg.get("symbol")
    ltp = msg.get("ltp")
    vol = msg.get("vol_traded_today")
    ts = msg.get("exch_feed_time")

    if not sym:
        return

    if sym not in day_open_price:
        day_open_price[sym] = ltp

    pct_change_map[sym] = ((ltp - day_open_price[sym]) / day_open_price[sym]) * 100

    handle_tick(sym, ltp, vol, ts)

def on_open():
    # subscribe to all unique stocks from sector map
    symbols = sorted({s for lst in SECTOR_MAP.values() for s in lst})
    ws.subscribe(symbols=symbols, data_type="SymbolUpdate")

# ============================================================
# ENGINE LOOP (SECTOR DECISION)
# ============================================================
def engine_loop():
    global SETTINGS, TICK_START_TS, SELECTED_STOCKS

    SETTINGS = read_settings()

    # Tick start time from Settings
    t = datetime.strptime(SETTINGS["TICK_START_TIME"], "%H:%M:%S")
    now = datetime.now()
    TICK_START_TS = int(
        t.replace(year=now.year, month=now.month, day=now.day).timestamp()
    )

    while True:
        now = datetime.now()

        maybe_run_sector_decision(
            now=now,
            pct_change_map=pct_change_map,
            bias_time=SETTINGS["BIAS_TIME"],
            threshold=float(SETTINGS["BIAS_THRESHOLD_PERCENT"]),
            max_up=float(SETTINGS["MAX_UP_PERCENT"]),
            max_dn=abs(float(SETTINGS["MAX_DOWN_PERCENT"])),
            buy_sector_count=int(SETTINGS["BUY_SECTOR_COUNT"]),
            sell_sector_count=int(SETTINGS["SELL_SECTOR_COUNT"]),
            sector_map=SECTOR_MAP,
            phase_b_switch=lambda s: SELECTED_STOCKS.update(s)
        )

        if now.strftime("%H:%M:%S") >= SETTINGS["AUTO_SQUAREOFF_TIME"]:
            break

        time.sleep(1)

# ============================================================
# START FYERS WS
# ============================================================
ws = data_ws.FyersDataSocket(
    access_token=FYERS_ACCESS_TOKEN,
    on_message=on_message,
    on_connect=on_open,
    reconnect=True
)

# ============================================================
# FLASK ENTRY POINT (LOCKED)
# ============================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    threading.Thread(target=ws.connect, daemon=True).start()
    threading.Thread(target=engine_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=port)
