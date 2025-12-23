# ============================================================
# candle_engine.py
# 5-minute candle engine
# ============================================================

from datetime import datetime
from ws_client import get_tick
from signal_engine import on_new_candle

CANDLE_SEC = 300

_candles = {}
_last_vol = {}

def _bucket(ts):
    return ts - (ts % CANDLE_SEC)

def start_candle_engine(runtime, bias_getter):
    print("🕯️ Candle engine started")

    while True:
        tick = get_tick()
        if not tick:
            continue

        if datetime.now().time() < runtime.tick_start_time():
            continue

        sym = tick["symbol"]
        ts = tick["ts"]
        ltp = tick["ltp"]
        vol = tick["volume"]

        bucket = _bucket(ts)
        c = _candles.get(sym)

        if not c or c["start"] != bucket:
            if c:
                prev = _last_vol.get(sym, c["cum_vol"])
                c["volume"] = c["cum_vol"] - prev
                _last_vol[sym] = c["cum_vol"]

                bias = bias_getter(sym)
                if bias:
                    on_new_candle(sym, c, bias)

            _candles[sym] = {
                "start": bucket,
                "open": ltp,
                "high": ltp,
                "low": ltp,
                "close": ltp,
                "cum_vol": vol
            }
        else:
            c["high"] = max(c["high"], ltp)
            c["low"] = min(c["low"], ltp)
            c["close"] = ltp
            c["cum_vol"] = vol
