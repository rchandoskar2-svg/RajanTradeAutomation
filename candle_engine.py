# ============================================================
# candle_engine.py
# Phase-A / Phase-B 5-minute candle engine (FIXED)
# ============================================================

import os
import time
from datetime import datetime
from collections import defaultdict, deque

from ws_client import get_tick
from config_runtime import RuntimeConfig

# ------------------------------------------------------------
# INTERNAL STATE
# ------------------------------------------------------------
CANDLE_SEC = 300

_phase = "A"                      # A = observation, B = trading
_selected_symbols = set()          # Phase-B stocks

runtime = None                     # RuntimeConfig
webapp_post = None                 # function(action, payload)

_candle_buf = {}
_last_day_vol = {}
_phaseA_candles = defaultdict(list)
_close_queue = deque()

# ------------------------------------------------------------
# UTILS
# ------------------------------------------------------------
def _direction(o, c):
    if c > o: return "GREEN"
    if c < o: return "RED"
    return "NEUTRAL"

def _bucket(ts):
    return ts - (ts % CANDLE_SEC)

# ------------------------------------------------------------
# INIT
# ------------------------------------------------------------
def init_engine(runtime_cfg, post_func):
    global runtime, webapp_post
    runtime = runtime_cfg
    webapp_post = post_func
    print("🕯️ Candle engine initialized")

# ------------------------------------------------------------
# PHASE SWITCH
# ------------------------------------------------------------
def switch_to_phase_b(selected_symbols: set):
    global _phase, _selected_symbols
    _phase = "B"
    _selected_symbols = set(selected_symbols)

    rows = []
    for sym in _selected_symbols:
        for c in _phaseA_candles.get(sym, []):
            rows.append(c)

    if rows:
        webapp_post("pushCandleEngine", {"candles": rows})

# ------------------------------------------------------------
# CORE LOOP
# ------------------------------------------------------------
def start_candle_engine():
    print("🕯️ Candle engine started")

    while True:
        tick = get_tick(timeout=1)
        if not tick:
            _process_close_queue()
            continue

        now = datetime.now()
        if not runtime or not runtime.is_tick_window_open(now):
            continue

        _handle_tick(tick)
        _process_close_queue()

# ------------------------------------------------------------
# TICK HANDLER
# ------------------------------------------------------------
def _handle_tick(tick):
    sym = tick["symbol"]
    ltp = tick["ltp"]
    vol = tick["volume"]
    ts  = tick["ts"]

    if _phase == "B" and sym not in _selected_symbols:
        return

    bucket = _bucket(ts)

    if sym not in _candle_buf:
        _candle_buf[sym] = {
            "start": bucket,
            "open": ltp,
            "high": ltp,
            "low": ltp,
            "close": ltp,
            "cum_vol": vol,
            "index": 1
        }
        _last_day_vol[sym] = vol
        return

    c = _candle_buf[sym]

    if c["start"] == bucket:
        c["high"] = max(c["high"], ltp)
        c["low"] = min(c["low"], ltp)
        c["close"] = ltp
        c["cum_vol"] = vol
    else:
        _close_queue.append(sym)
        _candle_buf[sym] = {
            "start": bucket,
            "open": ltp,
            "high": ltp,
            "low": ltp,
            "close": ltp,
            "cum_vol": vol,
            "index": c["index"] + 1
        }

# ------------------------------------------------------------
# CLOSE CANDLES (ANTI-SPIKE)
# ------------------------------------------------------------
def _process_close_queue(max_per_cycle=25):
    for _ in range(max_per_cycle):
        if not _close_queue:
            return

        sym = _close_queue.popleft()
        c = _candle_buf.get(sym)
        if not c:
            continue

        prev_vol = _last_day_vol.get(sym, 0)
        vol_diff = max(0, c["cum_vol"] - prev_vol)
        _last_day_vol[sym] = c["cum_vol"]

        row = {
            "symbol": sym,
            "time": datetime.fromtimestamp(c["start"]).strftime("%Y-%m-%d %H:%M:%S"),
            "timeframe": "5",
            "open": c["open"],
            "high": c["high"],
            "low": c["low"],
            "close": c["close"],
            "volume": vol_diff,
            "candle_index": c["index"],
            "direction": _direction(c["open"], c["close"])
        }

        if _phase == "A" and c["index"] <= 3:
            _phaseA_candles[sym].append(row)
            webapp_post("pushCandle", {"candles": [row]})
        elif _phase == "B":
            webapp_post("pushCandleEngine", {"candles": [row]})
