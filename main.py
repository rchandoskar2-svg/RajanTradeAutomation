# ============================================================
# RajanTradeAutomation – FINAL MAIN.PY (PRODUCTION SAFE)
# Flask + FYERS WS + Google Sheets (WebApp.gs)
# TIME-SHIFT READY + WS → CANDLE FIXED
# ============================================================

import os
import time
import threading
from datetime import datetime
import requests
from flask import Flask, request, jsonify
from fyers_apiv3.FyersWebsocket import data_ws

from ws_client import enqueue_tick
from config_runtime import RuntimeConfig
from candle_engine import init_engine, run_candle_engine
from sector_engine import maybe_run_sector_decision
from sector_mapping import SECTOR_MAP

# ============================================================
# ENVIRONMENT VARIABLES (LOCKED)
# ============================================================

WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

if not WEBAPP_URL or not FYERS_ACCESS_TOKEN:
    raise Exception("Missing required ENV variables")

# ============================================================
# GLOBAL STATE
# ============================================================

runtime = RuntimeConfig(WEBAPP_URL)
runtime.refresh()

pct_change_map = {}        # symbol -> %change
ws_connected = False
engine_started = False

# ============================================================
# SAFE TIME HELPERS
# ============================================================

def now_dt():
    return datetime.now()

# ============================================================
# WEBAPP COMMUNICATION
# ============================================================

def call_webapp(action, payload=None, timeout=10):
    try:
        return requests.post(
            WEBAPP_URL,
            json={"action": action, "payload": payload or {}},
            timeout=timeout
        ).json()
    except Exception:
        return None

# ============================================================
# FYERS WEBSOCKET CALLBACKS
# ============================================================

def on_message(msg):
    """
    WS → enqueue_tick (CRITICAL FIX)
    """
    try:
        symbol = msg.get("symbol")
        ltp = msg.get("ltp")
        volume = msg.get("vol_traded_today", 0)
        exch_ts = msg.get("exch_feed_time")

        if not symbol or ltp is None or exch_ts is None:
            return

        enqueue_tick(
            symbol=symbol,
            ltp=ltp,
            volume=volume,
            exch_ts=exch_ts
        )

        # % change cache (for sector engine)
        if "percent_change" in msg:
            pct_change_map[symbol] = msg["percent_change"]

    except Exception as e:
        print("WS on_message error:", e)


def on_connect():
    global ws_connected
    ws_connected = True
    print("✅ FYERS WS connected")


def on_error(err):
    print("❌ FYERS WS error:", err)


def on_close():
    print("⚠️ FYERS WS closed")

# ============================================================
# FYERS WS INIT
# ============================================================

ws = data_ws.FyersDataSocket(
    access_token=FYERS_ACCESS_TOKEN,
    on_message=on_message,
    on_connect=on_connect,
    on_error=on_error,
    on_close=on_close,
    reconnect=True
)

def start_ws():
    ws.connect()

# ============================================================
# ENGINE SUPERVISOR LOOP
# ============================================================

def supervisor_loop():
    global engine_started

    print("▶ Supervisor started")

    while True:
        runtime.refresh()
        now = now_dt()

        # Start candle engine once tick window opens
        if not engine_started and runtime.is_tick_window_open(now):
            print("▶ Tick window open → starting candle engine")
            init_engine(runtime, call_webapp)
            threading.Thread(target=run_candle_engine, daemon=True).start()
            engine_started = True

        # Sector decision (Phase-B trigger)
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
            phase_b_switch=lambda syms: call_webapp(
                "pushState",
                {"items": [{"key": "PHASE", "value": "B"}]}
            )
        )

        time.sleep(1)

# ============================================================
# FLASK APP (LOCKED ROUTES)
# ============================================================

app = Flask(__name__)

@app.route("/")
def root():
    return "RajanTradeAutomation backend LIVE ✅"

@app.route("/ping")
def ping():
    return "PONG"

@app.route("/getSettings")
def api_get_settings():
    return jsonify({"ok": True, "settings": runtime.settings})

@app.route("/fyers-redirect")
def fyers_redirect():
    auth_code = request.args.get("auth_code", "")
    return f"<pre>{auth_code}</pre>"

# ============================================================
# MAIN ENTRY
# ============================================================

if __name__ == "__main__":
    print("🚀 Starting RajanTradeAutomation (TIME-SHIFT READY)")

    threading.Thread(target=start_ws, daemon=True).start()
    threading.Thread(target=supervisor_loop, daemon=True).start()

    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
