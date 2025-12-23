# ============================================================
# sector_engine.py
# Sector bias engine (runs once)
# ============================================================

_decision_done = False
_bias_map = {}

def run_sector_decision(runtime, pct_map, sector_map):
    global _decision_done
    if _decision_done:
        return

    from datetime import datetime
    if datetime.now().time() < runtime.bias_time():
        return

    for sector, symbols in sector_map.items():
        for sym in symbols:
            chg = pct_map.get(sym)
            if chg is None:
                continue
            if chg > 0:
                _bias_map[sym] = "BULLISH"
            elif chg < 0:
                _bias_map[sym] = "BEARISH"

    _decision_done = True
    print("✅ Sector bias locked")

def get_bias(symbol):
    return _bias_map.get(symbol)
