# ============================================================
# sector_engine.py
# Sector + Stock Selection Engine (09:25:05 snapshot)
# ============================================================

from datetime import datetime
from collections import defaultdict

# injected from main.py
runtime = None                  # RuntimeConfig
tick_snapshot = None            # dict: symbol -> %change
sector_map = None               # dict: sector -> [symbols]
switch_to_phase_b = None        # candle_engine.switch_to_phase_b

_decision_done = False
_selected_symbols = set()
_bias_map = {}                  # symbol -> BUY / SELL


# ------------------------------------------------------------
# INIT
# ------------------------------------------------------------
def init_engine(runtime_cfg, sector_mapping, phase_b_switch):
    global runtime, sector_map, switch_to_phase_b
    runtime = runtime_cfg
    sector_map = sector_mapping
    switch_to_phase_b = phase_b_switch


# ------------------------------------------------------------
# MAIN CHECK (CALLED FROM engine loop)
# ------------------------------------------------------------
def maybe_run_sector_decision(now: datetime, pct_change_map: dict):
    """
    pct_change_map: symbol -> %change (Day)
    """
    global _decision_done, _selected_symbols, _bias_map

    if _decision_done:
        return None

    if not runtime.is_bias_time(now):
        return None

    threshold = runtime.bias_threshold()
    max_up = runtime.max_up_percent()
    max_dn = abs(runtime.max_down_percent())

    bullish_sectors = []
    bearish_sectors = []

    # --------------------------------------------------------
    # SECTOR BREADTH CALC
    # --------------------------------------------------------
    for sector, symbols in sector_map.items():
        total = 0
        pos = 0
        neg = 0

        for sym in symbols:
            if sym not in pct_change_map:
                continue

            chg = pct_change_map[sym]
            total += 1
            if chg > 0:
                pos += 1
            elif chg < 0:
                neg += 1

        if total == 0:
            continue

        if (pos / total) * 100 >= threshold:
            bullish_sectors.append(sector)
        elif (neg / total) * 100 >= threshold:
            bearish_sectors.append(sector)

    # --------------------------------------------------------
    # LIMIT SECTORS (AS PER SETTINGS)
    # --------------------------------------------------------
    bullish_sectors = bullish_sectors[: runtime.buy_sector_count()]
    bearish_sectors = bearish_sectors[: runtime.sell_sector_count()]

    # --------------------------------------------------------
    # STOCK FILTER (± %change)
    # --------------------------------------------------------
    for sector in bullish_sectors:
        for sym in sector_map.get(sector, []):
            chg = pct_change_map.get(sym)
            if chg is None:
                continue
            if abs(chg) > max_up:
                continue
            _selected_symbols.add(sym)
            _bias_map[sym] = "BUY"

    for sector in bearish_sectors:
        for sym in sector_map.get(sector, []):
            chg = pct_change_map.get(sym)
            if chg is None:
                continue
            if abs(chg) > max_dn:
                continue
            _selected_symbols.add(sym)
            _bias_map[sym] = "SELL"

    # --------------------------------------------------------
    # ACTIVATE PHASE-B
    # --------------------------------------------------------
    if _selected_symbols:
        switch_to_phase_b(_selected_symbols)

    _decision_done = True
    return {
        "bullish_sectors": bullish_sectors,
        "bearish_sectors": bearish_sectors,
        "selected_symbols": list(_selected_symbols),
        "bias_map": _bias_map
    }


# ------------------------------------------------------------
# ACCESSORS (USED BY TRADE MANAGER)
# ------------------------------------------------------------
def get_bias(symbol):
    return _bias_map.get(symbol)

def get_selected_symbols():
    return _selected_symbols.copy()
