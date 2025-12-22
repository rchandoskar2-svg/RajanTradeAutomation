# ============================================================
# signal_engine.py
# Lowest Volume So Far + Color based Signal Engine
# FINAL STRATEGY LOGIC (LOCKED)
# ============================================================

from collections import defaultdict
from datetime import datetime

# ------------------------------------------------------------
# INTERNAL STATE
# ------------------------------------------------------------

# Per symbol candle tracking
candle_state = defaultdict(lambda: {
    "candles": [],                 # list of candle dicts
    "lowest_volume": None,         # lowest volume so far
    "pending_signal": None         # current active signal
})

# ------------------------------------------------------------
# UTILS
# ------------------------------------------------------------

def candle_color(open_, close_):
    if close_ > open_:
        return "GREEN"
    elif close_ < open_:
        return "RED"
    return "DOJI"


# ------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------
def on_new_candle(symbol, candle, bias, settings):
    """
    Called on every new 5-min candle for SELECTED stocks only
    """

    state = candle_state[symbol]
    candles = state["candles"]

    # Append candle
    candles.append(candle)

    idx = len(candles)
    volume = candle["volume"]
    open_ = candle["open"]
    close_ = candle["close"]
    high = candle["high"]
    low = candle["low"]

    color = candle_color(open_, close_)

    # --------------------------------------------------------
    # Phase-A: First two candles → only volume tracking
    # --------------------------------------------------------
    if idx <= 2:
        _update_lowest_volume(state, volume)
        return None

    # --------------------------------------------------------
    # Phase-B: From 3rd candle onwards
    # --------------------------------------------------------

    is_lowest = _is_lowest_volume(state, volume)

    # Cancel old pending order if new lower volume appears
    if is_lowest and state["pending_signal"]:
        state["pending_signal"] = None

    # BUY LOGIC (BULLISH BIAS)
    if bias == "BULLISH":
        if color == "RED" and is_lowest:
            signal = _create_buy_signal(
                symbol, candle, settings
            )
            state["pending_signal"] = signal
            return signal

    # SELL LOGIC (BEARISH BIAS)
    if bias == "BEARISH":
        if color == "GREEN" and is_lowest:
            signal = _create_sell_signal(
                symbol, candle, settings
            )
            state["pending_signal"] = signal
            return signal

    return None


# ------------------------------------------------------------
# LOWEST VOLUME LOGIC
# ------------------------------------------------------------

def _update_lowest_volume(state, volume):
    if state["lowest_volume"] is None:
        state["lowest_volume"] = volume
    else:
        state["lowest_volume"] = min(state["lowest_volume"], volume)


def _is_lowest_volume(state, volume):
    if state["lowest_volume"] is None:
        state["lowest_volume"] = volume
        return True

    if volume < state["lowest_volume"]:
        state["lowest_volume"] = volume
        return True

    return False


# ------------------------------------------------------------
# SIGNAL BUILDERS
# ------------------------------------------------------------

def _create_buy_signal(symbol, candle, settings):
    risk_amt = float(settings.get("PER_TRADE_RISK", 500))

    entry = candle["high"]
    sl = candle["low"]
    risk_per_share = max(entry - sl, 0.01)

    qty = int(risk_amt // risk_per_share)

    return {
        "symbol": symbol,
        "direction": "BUY",
        "signal_time": _now(),
        "candle_index": candle["index"],
        "open": candle["open"],
        "high": candle["high"],
        "low": candle["low"],
        "close": candle["close"],
        "entry_price": entry,
        "sl": sl,
        "target_price": entry + (risk_per_share * 3),
        "risk_per_share": risk_per_share,
        "qty": qty,
        "rr": 3,
        "status": "PENDING"
    }


def _create_sell_signal(symbol, candle, settings):
    risk_amt = float(settings.get("PER_TRADE_RISK", 500))

    entry = candle["low"]
    sl = candle["high"]
    risk_per_share = max(sl - entry, 0.01)

    qty = int(risk_amt // risk_per_share)

    return {
        "symbol": symbol,
        "direction": "SELL",
        "signal_time": _now(),
        "candle_index": candle["index"],
        "open": candle["open"],
        "high": candle["high"],
        "low": candle["low"],
        "close": candle["close"],
        "entry_price": entry,
        "sl": sl,
        "target_price": entry - (risk_per_share * 3),
        "risk_per_share": risk_per_share,
        "qty": qty,
        "rr": 3,
        "status": "PENDING"
    }


# ------------------------------------------------------------
# TIME
# ------------------------------------------------------------

def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
