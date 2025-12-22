# ============================================================
# sector_engine.py
# Sector + Stock Selection Engine (09:25:05 snapshot)
# ============================================================

from datetime import datetime

_decision_done = False
_selected_symbols = set()
_bias_map = {}   # symbol -> BUY / SELL


def maybe_run_sector_decision(
    now: datetime,
    pct_change_map: dict,
    *,
    bias_time: str,
    threshold: float,
    max_up: float,
    max_dn: float,
    buy_sector_count: int,
    sell_sector_count: int,
    sector_map: dict,
    phase_b_switch
):
    """
    pct_change_map: symbol -> %change (day)
    """

    global _decision_done, _selected_symbols, _bias_map

    if _decision_done:
        return None

    if now.strftime("%H:%M:%S") < bias_time:
        return None

    bullish_sectors = []
    bearish_sectors = []

    # --------------------------------------------------------
    # SECTOR BREADTH
    # --------------------------------------------------------
    for sector, symbols in sector_map.items():
        total = pos = neg = 0

        for sym in symbols:
            chg = pct_change_map.get(sym)
            if chg is None:
                continue

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

    bullish_sectors = bullish_sectors[:buy_sector_count]
    bearish_sectors = bearish_sectors[:sell_sector_count]

    # --------------------------------------------------------
    # STOCK FILTER (± %change)
    # --------------------------------------------------------
    for sector in bullish_sectors:
        for sym in sector_map.get(sector, []):
            chg = pct_change_map.get(sym)
            if chg is None or abs(chg) > max_up:
                continue
            _selected_symbols.add(sym)
            _bias_map[sym] = "BUY"

    for sector in bearish_sectors:
        for sym in sector_map.get(sector, []):
            chg = pct_change_map.get(sym)
            if chg is None or abs(chg) > max_dn:
                continue
            _selected_symbols.add(sym)
            _bias_map[sym] = "SELL"

    # --------------------------------------------------------
    # ACTIVATE PHASE-B
    # --------------------------------------------------------
    if _selected_symbols:
        phase_b_switch(_selected_symbols)

    _decision_done = True

    return {
        "bullish_sectors": bullish_sectors,
        "bearish_sectors": bearish_sectors,
        "selected_symbols": list(_selected_symbols),
        "bias_map": _bias_map
    }


def get_bias(symbol):
    return _bias_map.get(symbol)


def get_selected_symbols():
    return _selected_symbols.copy()
