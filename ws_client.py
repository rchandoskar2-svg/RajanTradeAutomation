# ============================================================
# ws_client.py
# Ultra-fast WS tick receiver (NO business logic)
# ============================================================

import queue
from datetime import datetime

# ------------------------------------------------------------
# GLOBAL TICK QUEUE
# ------------------------------------------------------------
TICK_QUEUE = queue.Queue(maxsize=200000)   # large buffer, safe for bursts


# ------------------------------------------------------------
# TICK OBJECT FORMAT (STANDARDIZED)
# ------------------------------------------------------------
def build_tick(symbol, ltp, volume, exch_ts):
    """
    Normalize raw WS tick into internal format.
    NO processing here.
    """
    return {
        "symbol": symbol,
        "ltp": float(ltp),
        "volume": int(volume),
        "ts": int(exch_ts),                  # exchange epoch seconds
        "recv_time": datetime.now()          # local receive time
    }


# ------------------------------------------------------------
# ENQUEUE (CALLED FROM main.py WS CALLBACK)
# ------------------------------------------------------------
def enqueue_tick(symbol, ltp, volume, exch_ts):
    try:
        tick = build_tick(symbol, ltp, volume, exch_ts)
        TICK_QUEUE.put_nowait(tick)
    except queue.Full:
        # silently drop if queue is full (better than blocking WS)
        pass


# ------------------------------------------------------------
# DEQUEUE (CALLED FROM candle_engine)
# ------------------------------------------------------------
def get_tick(timeout=1):
    try:
        return TICK_QUEUE.get(timeout=timeout)
    except queue.Empty:
        return None
