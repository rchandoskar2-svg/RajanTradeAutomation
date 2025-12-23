# ============================================================
# RajanTradeAutomation – FINAL MAIN.PY
# FYERS WS RUNS IN DEDICATED NON-DAEMON THREAD
# ============================================================

import os
import time
import threading
from datetime import datetime
import requests
from flask import Flask, jsonify
from fyers_apiv3.FyersWebsocket import data_ws

from ws_client import enqueue_tick
from config_runtime import RuntimeConfig
from candle_engine import init_engine, run_candle_engine
from sector_engine import maybe_run_sector_decision
from sector_mapping import SECTOR_MAP

# ============================================================
# ENV
# ============================================================

WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
PORT = int(os.getenv("PORT", "10000"))

if not WEBAPP_URL or not FYERS_ACCESS_TOKEN:
    raise Exception("Missing ENV vars")

# ============================================================
# GLOBALS
# ============================================================

runtime = RuntimeConfig(WEBAPP_URL)
runtime.refresh()

pct_change_map = {}
engine_started = False

# ============================================================
# WEBAPP CALL
# ============================================================

def call_webapp(action, payload=None):
    try:
        return requests.post(
            WEBAPP_URL,
            json={"action": action, "payload": payload or {}},
            timeout=5
        ).json()
    except Exception as e:
        print("WebApp error:", e)
        return None

# ============================================================
# FYERS CALLBACKS
# ============================================================

def on_message(msg):
    try:
        symbol = msg.get("symbol")
        ltp = msg.get("ltp")
        vol = msg.get("vol_traded_today", 0)
        exch_ts = msg.get("exch_feed_time")

        if not symbol or ltp is None or exch_ts is None:
            return

        enqueue_tick(symbol, ltp, vol, exch_ts)

        if "percent_change" in msg:
            pct_change_map[symbol] = msg["percent_change"]

    except Exception as e:
        print("on_message error:", e)


def on_connect():
    print("✅ FYERS WS connected")

    symbols = []
    for lst in SECTOR_MAP.values():
        symbols.extend(lst)

    symbols = list(set(symbols))
    print(f"▶ Subscribing to {len(symbols)} symbols")

    ws.subscribe(
        symbols=symbols,
        data_type="SymbolUpdate"
    )


def on_error(err):
    print("❌ FYERS WS error:", err)


def on_close():
    print("⚠️ FYERS WS closed")

# ============================================================
# FYERS WS OBJECT
# ============================================================

ws = data_ws.FyersDataSocket(
    access_token=FYERS_ACCESS_TOKEN,
    on_message=on_message,
    on_connect=on_connect,
    on_error=on_error,
    on_close=on_close,
    reconnect=True
)

# ============================================================
# FYERS WS THREAD (NON-DAEMON)
# ============================================================

def run_fyers_ws():
    print("▶ Starting FYERS WS thread")
    ws.connect()
    ws.keep_running()   # BLOCKS HERE (THIS IS REQUIRED)

# ============================================================
# SUPERVISOR
# ============================================================

def supervisor():
    global engine_started
    print("▶ Supervisor started")

    while True:
        runtime.refresh()
        now = datetime.now()

        if not engine_started and runtime.is_tick_window_open(now):
            print("▶ Tick window open → starting candle engine")
            init_engine(runtime, call_webapp)
            threading.Thread(
                target=run_candle_engine,
                daemon=True
            ).start()
            engine_started = True

        maybe_run_sector_decision(
            now=now,
            pct_change_map=pct_change_map,
            bias_time=runtime.bias_time().strftime("%H:%M:%S"),
            threshold=runtime.bias_threshold(),
            max_up=runtime.max_up_percent(),
            max_dn=runtime.max_down_percent(),
            buy_sector_count=runtime.buy_sector_count(),
            sell_sector_count=runtime.sell_sector_count(),
            sector_map=SECTOR_MAP,
            phase_b_switch=lambda syms: print(
                f"▶ Phase-B activated ({len(syms)} symbols)"
            )
        )

        time.sleep(1)

# ============================================================
# FLASK APP
# ============================================================

app = Flask(__name__)

@app.route("/")
def root():
    return "RajanTradeAutomation LIVE ✅"

@app.route("/ping")
def ping():
    return "PONG"

@app.route("/getSettings")
def get_settings():
    return jsonify({"ok": True, "settings": runtime.settings})

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("🚀 Starting RajanTradeAutomation (RENDER SAFE)")

    # 1️⃣ Start FYERS WS FIRST (NON-DAEMON)
    ws_thread = threading.Thread(target=run_fyers_ws)
    ws_thread.start()

    # 2️⃣ Start supervisor
    threading.Thread(target=supervisor, daemon=True).start()

    # 3️⃣ Start Flask (LAST)
    app.run(host="0.0.0.0", port=PORT)
