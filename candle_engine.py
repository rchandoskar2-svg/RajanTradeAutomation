# ============================================================
# candle_engine.py
# ============================================================

import time
import threading
from datetime import datetime
from ws_client import get_tick
from sector_engine import maybe_run_sector_decision
from sector_mapping import SECTOR_MAP
from config_runtime import RuntimeConfig

CANDLE_SEC = 300
candles = {}
last_vol = {}

runtime = RuntimeConfig(webapp_url=os.getenv("WEBAPP_URL", ""))

def _bucket(ts):
    return ts - (ts % CANDLE_SEC)

def candle_loop():
    print("🕯️ Candle engine STARTED")

    while True:
        tick = get_tick(timeout=1)
        if not tick:
            continue

        sym = tick["symbol"]
        ltp = tick["ltp"]
        vol = tick["volume"]
        ts  = tick["ts"]

        if not sym:
            continue

        start = _bucket(ts)
        c = candles.get(sym)

        if not c or c["start"] != start:
            if c:
                prev = last_vol.get(sym, c["cum_vol"])
                real_vol = c["cum_vol"] - prev
                last_vol[sym] = c["cum_vol"]

                print(
                    f"🟩 5m {sym} "
                    f"O:{c['open']} H:{c['high']} "
                    f"L:{c['low']} C:{c['close']} V:{real_vol}"
                )

            candles[sym] = {
                "start": start,
                "open": ltp,
                "high": ltp,
                "low": ltp,
                "close": ltp,
                "cum_vol": vol
            }
        else:
            c["high"] = max(c["high"], ltp)
            c["low"]  = min(c["low"], ltp)
            c["close"] = ltp
            c["cum_vol"] = vol

def start_candle_engine():
    runtime.refresh()

    symbols = set()
    for v in SECTOR_MAP.values():
        symbols.update(v)

    threading.Thread(target=candle_loop, daemon=True).start()
    return symbols
