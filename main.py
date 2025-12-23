# ============================================================
# RajanTradeAutomation – FINAL MAIN.PY (ABSOLUTE FIX)
# FYERS WS + SUBSCRIBE + KEEP_RUNNING + TIME-SHIFT SAFE
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
# ENVIRONMENT VARIABLES
# ============================================================

WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

if not WEBAPP_URL or not FYERS_ACCESS_TOKEN:
    raise Exception("Missing WEBAPP_URL or FYERS_ACCESS_TOKEN")

# ============================================================
# GLOBAL STATE
# ============================================================

runtime = RuntimeConfig(WEBAPP_URL)
runtime.refresh()

pct_change_map = {}
engine_started = False
ws_connected = False

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
    except Exception:
        return None

# ============================================================
# FYERS WS CALLBACKS
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
        print("❌ on_message error:", e)


def on_connect():
    global ws_connected
    ws_connected = True
    print("✅ FYERS WS connected")

    # -------- SUBSCRIBE (MANDATORY) --------
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
    ws.keep_running()   # 🔥 THIS WAS THE ROOT CAUSE

# ============================================================
# SUPERVISOR LOOP
# ============================================================

def supervisor():
    global engine_started

    print("▶ Supervisor started")

    while True:
        runtime.refresh()
        now = datetime.now()

        # Start candle engine after tick window opens
        if not engine_started and runtime.is_tick_window_open(now):
            print("▶ Tic
