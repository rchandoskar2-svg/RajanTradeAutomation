# ============================================================
# ws_client.py
# Tick receiver queue
# ============================================================

import queue
from datetime import datetime

TICK_QUEUE = queue.Queue(maxsize=200000)

def push_tick(symbol, ltp, volume, ts):
    try:
        TICK_QUEUE.put_nowait({
            "symbol": symbol,
            "ltp": float(ltp),
            "volume": int(volume),
            "ts": int(ts),
            "recv": datetime.now()
        })
    except queue.Full:
        pass

def get_tick(timeout=1):
    try:
        return TICK_QUEUE.get(timeout=timeout)
    except queue.Empty:
        return None
