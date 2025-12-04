# ==========================================================
# RajanTradeAutomation – main.py (NEW STRATEGY LIVE ENGINE)
# Version: 1.1 – NSE+Fyers wired, WebSocket REALTIME ON
# ==========================================================

import os
import json
import time
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from flask import Flask, request, jsonify

from fyers_apiv3 import fyersModel
from fyers_apiv3.FyersWebsocket import data_ws

# ----------------------------------------------------------
# ENVIRONMENT
# ----------------------------------------------------------
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY", "").strip()
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
INTERVAL_SECS = int(os.getenv("INTERVAL_SECS", "60"))

IST = ZoneInfo("Asia/Kolkata")

# ----------------------------------------------------------
# GLOBALS
# ----------------------------------------------------------
app = Flask(__name__)

# Fyers REST client
fyers_rest = fyersModel.FyersModel(
    client_id=FYERS_CLIENT_ID,
    token=FYERS_ACCESS_TOKEN,
    log_path=""
)

# NSE session (common headers)
nse_session = requests.Session()
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/119.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nseindia.com/",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive"
}

engine_state = {
    "day": None,
    "bias": None,                 # BUY / SELL
    "selected_sectors": [],
    "selected_symbols": [],
    "symbols_direction": {},
    "prepared": False,
    "ws_started": False,
    "settings": {},
    "symbols": {}
}

engine_lock = threading.Lock()
fyers_ws = None

# ----------------------------------------------------------
# SMALL UTILS
# ----------------------------------------------------------
def now_ist():
    return datetime.now(tz=IST)

def today_str():
    return now_ist().strftime("%Y-%m-%d")

def log(msg):
    print(f"[{now_ist().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def post_webapp(action: str, payload: dict):
    if not WEBAPP_URL:
        log("WEBAPP_URL missing.")
        return None
    try:
        resp = requests.post(WEBAPP_URL, json={"action": action, "payload": payload}, timeout=10)
        if resp.status_code == 200:
            try:
                return resp.json()
            except Exception:
                return {}
        else:
            log(f"WebApp {action} HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        log(f"WebApp {action} error: {e}")
    return None

def fetch_settings_from_sheet():
    res = post_webapp("getSettings", {})
    if res and res.get("ok"):
        return res.get("settings", {})
    return {}

# ----------------------------------------------------------
# NSE HELPERS
# ----------------------------------------------------------
def nse_get(url, params=None):
    """
    Generic NSE GET with session & headers.
    """
    try:
        resp = nse_session.get(url, headers=NSE_HEADERS, params=params, timeout=10)
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}")
        return resp.json()
    except Exception as e:
        log(f"NSE GET fail {url}: {e}")
        return None

# ----------------------------------------------------------
# 1) MARKET BREADTH – ADV / DEC
# ----------------------------------------------------------
def fetch_market_breadth():
    """
    Primary: NSE 'allIndices' – pick NIFTY 50 advances/declines.
    Fallback: if fail, use equal numbers (no bias).
    """
    # Unofficial NSE endpoint
    url = "https://www.nseindia.com/api/allIndices"
    data = nse_get(url)
    if data and "data" in data:
        try:
            for idx in data["data"]:
                name = idx.get("index") or idx.get("indexSymbol")
                if not name:
                    continue
                if name.upper().startswith("NIFTY 50"):
                    adv = idx.get("advances") or idx.get("advance")
                    dec = idx.get("declines") or idx.get("decline")
                    if isinstance(adv, dict):
                        adv = adv.get("advances")
                    if isinstance(dec, dict):
                        dec = dec.get("declines")
                    adv = int(adv or 0)
                    dec = int(dec or 0)
                    log(f"NSE breadth: adv={adv}, dec={dec}")
                    return adv, dec
        except Exception as e:
            log(f"parse breadth error: {e}")

    log("fetch_market_breadth: NSE failed, fallback adv=dec=0 (no bias).")
    return 0, 0

# ----------------------------------------------------------
# 2) SECTOR PERFORMANCE – % CHANGE
# ----------------------------------------------------------
# List of sector indices we care about
SECTOR_INDEX_NAMES = [
    "NIFTY PSU BANK",
    "NIFTY OIL & GAS",
    "NIFTY ENERGY",
    "NIFTY PHARMA",
    "NIFTY CONSUMER DURABLES",
    "NIFTY IT",
    "NIFTY INFRASTRUCTURE",
    "NIFTY CONSUMPTION",
    "NIFTY AUTO",
    "NIFTY HEALTHCARE",
    "NIFTY METAL",
    "NIFTY BANK",
    "NIFTY PRIVATE BANK",
    "NIFTY FINANCIAL SERVICES",
    "NIFTY FINANCIAL SERVICES 25/50",
    "NIFTY MEDIA"
]

def fetch_sector_performance():
    """
    Primary: NSE 'allIndices' – percentChange per index.
    Returns list of {sector_name, sector_code, per_chg, advances, declines}
    """
    url = "https://www.nseindia.com/api/allIndices"
    data = nse_get(url)
    sectors = []

    if data and "data" in data:
        try:
            for idx in data["data"]:
                name = (idx.get("index") or idx.get("indexSymbol") or "").upper()
                if name in SECTOR_INDEX_NAMES:
                    per_chg = float(idx.get("percentChange") or 0.0)
                    adv = idx.get("advances") or idx.get("advance")
                    dec = idx.get("declines") or idx.get("decline")
                    if isinstance(adv, dict):
                        adv = adv.get("advances")
                    if isinstance(dec, dict):
                        dec = dec.get("declines")
                    sectors.append({
                        "sector_name": name,
                        "sector_code": name,  # for now identical
                        "per_chg": per_chg,
                        "advances": int(adv or 0),
                        "declines": int(dec or 0)
                    })
            log(f"fetch_sector_performance: got {len(sectors)} sectors from NSE.")
        except Exception as e:
            log(f"parse sectors error: {e}")

    return sectors

# ----------------------------------------------------------
# 3) UNIVERSE – FnO + SECTOR MAPPING (approx via NSE)
# ----------------------------------------------------------
def fetch_constituents_for_index(index_name):
    """
    NSE equity-stockIndices?index=INDEX – gives stocks for that sector/index.
    """
    url = "https://www.nseindia.com/api/equity-stockIndices"
    data = nse_get(url, params={"index": index_name})
    out = []
    if data and "data" in data:
        try:
            for row in data["data"]:
                sym = row.get("symbol")
                if not sym:
                    continue
                out.append({
                    "symbol": sym,
                    "name": row.get("meta", {}).get("companyName") or sym,
                    "sector": index_name,
                    "is_fno": True,     # आपण Fyers वर quote मिळतो का ते नंतर check करू
                    "enabled": True
                })
        except Exception as e:
            log(f"parse constituents error for {index_name}: {e}")
    return out

def fyers_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if ":" not in s:
        s = "NSE:" + s
    if not s.endswith("-EQ"):
        s = s + "-EQ"
    return s

def fetch_fno_universe():
    """
    Approximated universe:
    - For each sector index we care about, get constituents from NSE
    - We'll later filter to only symbols for which Fyers quotes succeed.
    """
    universe = []
    seen = set()

    for idx_name in SECTOR_INDEX_NAMES:
        cons = fetch_constituents_for_index(idx_name)
        for row in cons:
            sym = row["symbol"].upper()
            if sym in seen:
                continue
            seen.add(sym)
            row["symbol"] = fyers_symbol(sym)
            universe.append(row)

    log(f"fetch_fno_universe: total approximate symbols={len(universe)}")
    return universe

# ----------------------------------------------------------
# FYERS REST HELPERS (quotes + history)
# ----------------------------------------------------------
def fyers_quotes(symbols):
    """
    Fetch LTP, %change, volume for given Fyers symbols.
    """
    if not symbols:
        return {}

    try:
        symbol_str = ",".join(symbols)
        data = {"symbols": symbol_str}
        resp = fyers_rest.quotes(data=data)
        q = {}
        for item in resp.get("d", []):
            sym = item.get("n")
            v = item.get("v", {}) or {}
            q[sym] = {
                "ltp": v.get("lp", 0.0),
                "percent_change": v.get("chp", 0.0),
                "volume": v.get("volume", 0)
            }
        return q
    except Exception as e:
        log(f"fyers_quotes error: {e}")
        return {}

def fyers_5min_history(symbol, start: datetime, end: datetime):
    """
    Use Fyers history API (5m) for given day, filter 09:15–09:30.
    """
    try:
        data = {
            "symbol": symbol,
            "resolution": "5",
            "date_format": "1",
            "range_from": start.strftime("%Y-%m-%d"),
            "range_to": end.strftime("%Y-%m-%d"),
            "cont_flag": "1"
        }
        resp = fyers_rest.history(data=data)
        candles = []
        for row in resp.get("candles", []):
            ts, o, h, l, c, v = row
            t = datetime.fromtimestamp(ts, tz=IST)
            if start <= t <= end:
                candles.append({
                    "time": t,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": v
                })
        return candles
    except Exception as e:
        log(f"fyers_5min_history error for {symbol}: {e}")
        return []

# ----------------------------------------------------------
# SELECTION ENGINE (09:26–09:29)
# ----------------------------------------------------------
def decide_bias(adv, dec):
    if adv > dec:
        return "BUY"
    elif dec > adv:
        return "SELL"
    return None

def pick_sectors(bias, sectors, settings):
    if not sectors:
        return []

    if bias == "BUY":
        # सर्वात जास्त % up
        sorted_sec = sorted(sectors, key=lambda x: x.get("per_chg", 0), reverse=True)
        count = int(settings.get("BUY_SECTOR_COUNT", 2))
    elif bias == "SELL":
        # सर्वात जास्त % down (bottom negative)
        sorted_sec = sorted(sectors, key=lambda x: x.get("per_chg", 0))
        count = int(settings.get("SELL_SECTOR_COUNT", 2))
    else:
        return []

    return sorted_sec[:count]

def filter_stocks_by_percent(bias, universe_rows, quotes_map, settings):
    max_up = float(settings.get("MAX_UP_PERCENT", 2.5))
    max_down = float(settings.get("MAX_DOWN_PERCENT", -2.5))

    selected = []
    for row in universe_rows:
        sym = row["symbol"]
        q = quotes_map.get(sym)
        if not q:
            continue
        pc = q["percent_change"]
        if bias == "BUY":
            if 0 < pc <= max_up:
                selected.append((sym, row["sector"], pc, q))
        elif bias == "SELL":
            if max_down <= pc < 0:
                selected.append((sym, row["sector"], pc, q))

    if bias == "BUY":
        selected.sort(key=lambda x: x[2], reverse=True)   # highest +% first
    else:
        selected.sort(key=lambda x: x[2])                 # lowest (most negative) first

    max_stocks = 10
    return selected[:max_stocks]

def prepare_day_if_needed():
    with engine_lock:
        today = today_str()
        if engine_state["day"] == today and engine_state["prepared"]:
            return

    # Strictly between 09:26–09:30
    now = now_ist()
    hhmm = now.strftime("%H:%M")
    if not ("09:26" <= hhmm < "09:30"):
        return

    log("Preparing day – settings + breadth + sector + universe…")
    settings = fetch_settings_from_sheet()
    adv, dec = fetch_market_breadth()
    bias = decide_bias(adv, dec)
    log(f"Market breadth adv={adv} dec={dec} bias={bias}")

    sectors = fetch_sector_performance()
    chosen_sectors = pick_sectors(bias, sectors, settings)

    # Universe from NSE (approx) + filter to chosen sectors
    universe = fetch_fno_universe()
    chosen_sector_names = [s["sector_name"] for s in chosen_sectors]
    chosen_symbols_rows = [u for u in universe if u.get("sector") in chosen_sector_names]

    # Quotes for those symbols (filter non-Fyers)
    quotes_map = fyers_quotes([u["symbol"] for u in chosen_symbols_rows])
    chosen_symbols_rows = [u for u in chosen_symbols_rows if u["symbol"] in quotes_map]

    filtered = filter_stocks_by_percent(bias, chosen_symbols_rows, quotes_map, settings)
    final_symbols = [row[0] for row in filtered]
    symbols_direction = {sym: bias for sym in final_symbols}

    # Update StockList sheet
    stocks_payload = []
    for sym, sector, pc, q in filtered:
        stocks_payload.append({
            "symbol": sym,
            "direction_bias": bias,
            "sector": sector,
            "%chg": pc,
            "ltp": q["ltp"],
            "volume": q["volume"],
            "selected": True
        })
    post_webapp("updateStockList", {"stocks": stocks_payload})

    # Push Universe + sectors snapshot (optional)
    post_webapp("syncUniverse", {"universe": universe})
    post_webapp("updateSectorPerf", {"sectors": sectors})

    # First 3 candles via history (09:15–09:30)
    history_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    history_end = now.replace(hour=9, minute=30, second=0, microsecond=0)

    symbol_states = {}
    for sym in final_symbols:
        candles = fyers_5min_history(sym, history_start, history_end)
        candles_sorted = sorted(candles, key=lambda x: x["time"])
        rows_for_sheet = []
        lowest_v = None
        idx = 1
        for c in candles_sorted:
            volume = c["volume"]
            if lowest_v is None or volume < lowest_v:
                lowest_v = volume
            rows_for_sheet.append({
                "symbol": sym,
                "time": c["time"].isoformat(),
                "timeframe": "5m",
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": volume,
                "candle_index": idx,
                "lowest_volume_so_far": lowest_v,
                "is_signal": False,
                "direction": bias
            })
            idx += 1

        if rows_for_sheet:
            post_webapp("pushCandle", {"candles": rows_for_sheet})

        symbol_states[sym] = {
            "candles": rows_for_sheet,
            "lowest_volume_so_far": lowest_v or 0,
            "signal_found": False,
            "signal_candle": None,
            "active_trade": None
        }

    with engine_lock:
        engine_state["day"] = today
        engine_state["bias"] = bias
        engine_state["selected_sectors"] = chosen_sector_names
        engine_state["selected_symbols"] = final_symbols
        engine_state["symbols_direction"] = symbols_direction
        engine_state["symbols"] = symbol_states
        engine_state["settings"] = settings
        engine_state["prepared"] = True

    log(f"Day prepared. Bias={bias}, symbols={final_symbols}")

# ----------------------------------------------------------
# WEBSOCKET HANDLERS (Fyers executive pattern)
# ----------------------------------------------------------
def onmessage_ws(message):
    try:
        if isinstance(message, str):
            msg = json.loads(message)
        else:
            msg = message
    except Exception:
        msg = message

    if not isinstance(msg, dict):
        return

    d = msg.get("d") or msg  # library sometimes nests inside 'd'
    symbol = d.get("symbol") or d.get("symbol_name")
    if not symbol:
        return

    ltp = d.get("ltp") or d.get("last_traded_price") or d.get("price") or 0.0
    ts = d.get("timestamp") or d.get("tt") or int(time.time())
    t = datetime.fromtimestamp(int(ts), tz=IST)

    # volume tick (optional)
    vol_tick = d.get("volume") or 1

    handle_tick(symbol, float(ltp), t, int(vol_tick))

def onerror_ws(message):
    log(f"[WS ERROR] {message}")

def onclose_ws(message):
    log(f"[WS CLOSED] {message}")

def onopen_ws():
    data_type = "SymbolUpdate"
    with engine_lock:
        symbols = engine_state.get("selected_symbols", [])
    if not symbols:
        log("WS onopen: no symbols.")
        return
    log(f"WS onopen subscribing: {symbols}")
    fyers_ws.subscribe(symbols=symbols, data_type=data_type)
    fyers_ws.keep_running()

def start_websocket_if_needed():
    global fyers_ws
    with engine_lock:
        symbols = engine_state.get("selected_symbols", [])
        ws_started = engine_state.get("ws_started", False)

    if ws_started or not symbols:
        return

    log("Starting Fyers WebSocket…")
    fyers_ws = data_ws.FyersDataSocket(
        access_token=FYERS_ACCESS_TOKEN,
        log_path="",
        litemode=False,
        write_to_file=False,
        reconnect=True,
        on_connect=onopen_ws,
        on_close=onclose_ws,
        on_error=onerror_ws,
        on_message=onmessage_ws
    )
    threading.Thread(target=fyers_ws.connect, daemon=True).start()
    with engine_lock:
        engine_state["ws_started"] = True

# ----------------------------------------------------------
# TICK → 5m CANDLE + SIGNAL / ENTRY
# ----------------------------------------------------------
def candle_bucket_time(t: datetime) -> datetime:
    minute = (t.minute // 5) * 5 + 5
    hour = t.hour
    if minute >= 60:
        minute -= 60
        hour += 1
    return t.replace(hour=hour, minute=minute, second=0, microsecond=0)

def handle_tick(symbol: str, ltp: float, t: datetime, vol_tick: int = 1):
    with engine_lock:
        sym_state = engine_state["symbols"].get(symbol)
        bias = engine_state.get("bias")
        settings = engine_state.get("settings", {})
    if not sym_state:
        return

    bucket_time = candle_bucket_time(t)
    candles = sym_state["candles"]

    if candles and candles[-1]["time"] == bucket_time.isoformat():
        c = candles[-1]
        c["high"] = max(c["high"], ltp)
        c["low"] = min(c["low"], ltp)
        c["close"] = ltp
        c["volume"] += vol_tick
    else:
        index = (candles[-1]["candle_index"] + 1) if candles else 1
        c = {
            "symbol": symbol,
            "time": bucket_time.isoformat(),
            "timeframe": "5m",
            "open": ltp,
            "high": ltp,
            "low": ltp,
            "close": ltp,
            "volume": vol_tick,
            "candle_index": index,
            "lowest_volume_so_far": sym_state.get("lowest_volume_so_far") or 0,
            "is_signal": False,
            "direction": bias
        }
        candles.append(c)

    # on every tick after bucket close, evaluate (approx)
    if t >= bucket_time:
        evaluate_candle(symbol)

def evaluate_candle(symbol: str):
    with engine_lock:
        sym_state = engine_state["symbols"].get(symbol)
        if not sym_state:
            return
        candles = sym_state["candles"]
        lowest_vol = sym_state.get("lowest_volume_so_far") or 0
        bias = engine_state["bias"]
        settings = engine_state["settings"]

    if not candles:
        return

    c = candles[-1]
    vol = c["volume"]
    o = c["open"]
    h = c["high"]
    l = c["low"]
    cl = c["close"]
    idx = c["candle_index"]

    if idx < 4:
        return

    if lowest_vol == 0 or vol < lowest_vol:
        lowest_vol = vol
    c["lowest_volume_so_far"] = lowest_vol

    is_signal = False
    direction = None
    if bias == "BUY":
        if o > cl and vol <= lowest_vol:
            is_signal = True
            direction = "BUY"
    elif bias == "SELL":
        if cl > o and vol <= lowest_vol:
            is_signal = True
            direction = "SELL"

    if not is_signal:
        with engine_lock:
            sym_state["lowest_volume_so_far"] = lowest_vol
        return

    entry_price = h if direction == "BUY" else l
    sl = l if direction == "BUY" else h
    risk_per_share = abs(entry_price - sl)
    rr = float(settings.get("RR_RATIO", 2.0) or 2.0)
    target_price = entry_price + rr * risk_per_share if direction == "BUY" else entry_price - rr * risk_per_share

    qty = 1
    per_trade_risk_en = str(settings.get("ENABLE_PER_TRADE_RISK", "TRUE")).upper() == "TRUE"
    if per_trade_risk_en and risk_per_share > 0:
        per_trade_risk = float(settings.get("PER_TRADE_RISK", 1000) or 1000.0)
        qty = int(per_trade_risk // risk_per_share) or 1

    signal_row = {
        "symbol": symbol,
        "direction": direction,
        "signal_time": c["time"],
        "candle_index": idx,
        "open": o,
        "high": h,
        "low": l,
        "close": cl,
        "entry_price": entry_price,
        "sl": sl,
        "target_price": target_price,
        "risk_per_share": risk_per_share,
        "rr": rr,
        "status": "PENDING"
    }
    post_webapp("pushSignal", {"signals": [signal_row]})

    trade_payload = {
        "symbol": symbol,
        "direction": direction,
        "entry_price": entry_price,
        "sl": sl,
        "target_price": target_price,
        "qty_total": qty,
        "entry_time": c["time"]
    }
    post_webapp("pushTradeEntry", trade_payload)

    with engine_lock:
        sym_state["lowest_volume_so_far"] = lowest_vol
        sym_state["signal_found"] = True
        sym_state["signal_candle"] = c
        sym_state["active_trade"] = {
            "direction": direction,
            "entry_price": entry_price,
            "sl": sl,
            "target_price": target_price,
            "qty_total": qty,
            "qty_remaining": qty,
            "half_exit_done": False,
            "full_exit_done": False
        }
        engine_state["symbols"][symbol] = sym_state

    log(f"SIGNAL+ENTRY {symbol} dir={direction} entry={entry_price} sl={sl} tgt={target_price} qty={qty}")

# ----------------------------------------------------------
# EXIT ENGINE – SL / TARGET HALF / 15:15
# ----------------------------------------------------------
def check_exits():
    with engine_lock:
        symbols_with_trades = [s for s, st in engine_state["symbols"].items() if st.get("active_trade")]
        settings = engine_state.get("settings", {})

    if not symbols_with_trades:
        return

    quotes = fyers_quotes(symbols_with_trades)
    partial_percent = float(settings.get("PARTIAL_EXIT_PERCENT", 50) or 50.0)

    now = now_ist()
    auto_sq_time = settings.get("AUTO_SQUAREOFF_TIME", "15:15")
    auto_h, auto_m = [int(x) for x in auto_sq_time.split(":")]
    auto_sq_dt = now.replace(hour=auto_h, minute=auto_m, second=0, microsecond=0)

    for sym in symbols_with_trades:
        with engine_lock:
            st = engine_state["symbols"][sym]
            trade = st["active_trade"]
        if not trade:
            continue

        q = quotes.get(sym)
        if not q:
            continue
        ltp = q["ltp"]
        direction = trade["direction"]
        entry = trade["entry_price"]
        sl = trade["sl"]
        tgt = trade["target_price"]
        qty_total = trade["qty_total"]
        qty_rem = trade["qty_remaining"]
        half_done = trade["half_exit_done"]
        full_done = trade["full_exit_done"]

        events = []

        # SL
        if direction == "BUY" and ltp <= sl and not full_done:
            pnl = (sl - entry) * qty_total
            events.append(("SL", qty_rem, sl, "SL-HIT", pnl))
        elif direction == "SELL" and ltp >= sl and not full_done:
            pnl = (entry - sl) * qty_total
            events.append(("SL", qty_rem, sl, "SL-HIT", pnl))

        # Target -> partial
        if not half_done and not full_done:
            if direction == "BUY" and ltp >= tgt:
                qty_half = int(qty_total * (partial_percent / 100.0)) or qty_total
                pnl = (tgt - entry) * qty_half
                events.append(("PARTIAL", qty_half, tgt, "PARTIAL", pnl))
            elif direction == "SELL" and ltp <= tgt:
                qty_half = int(qty_total * (partial_percent / 100.0)) or qty_total
                pnl = (entry - tgt) * qty_half
                events.append(("PARTIAL", qty_half, tgt, "PARTIAL", pnl))

        # Time-based final exit
        if now >= auto_sq_dt and not full_done:
            pnl = (ltp - entry) * qty_rem if direction == "BUY" else (entry - ltp) * qty_rem
            events.append(("FINAL", qty_rem, ltp, "CLOSED", pnl))

        for exit_type, exit_qty, exit_price, status, pnl in events:
            payload = {
                "symbol": sym,
                "exit_type": exit_type,
                "exit_qty": exit_qty,
                "exit_price": exit_price,
                "exit_time": now.isoformat(),
                "pnl": pnl,
                "status": status
            }
            post_webapp("pushTradeExit", payload)
            log(f"EXIT {exit_type} {sym} qty={exit_qty} price={exit_price} pnl={pnl}")

            with engine_lock:
                if exit_type == "PARTIAL":
                    trade["qty_remaining"] -= exit_qty
                    trade["half_exit_done"] = True
                    if trade["qty_remaining"] <= 0:
                        trade["full_exit_done"] = True
                else:
                    trade["qty_remaining"] = 0
                    trade["half_exit_done"] = True
                    trade["full_exit_done"] = True
                st["active_trade"] = trade
                engine_state["symbols"][sym] = st

# ----------------------------------------------------------
# ENGINE LOOP (heartbeat)
# ----------------------------------------------------------
def engine_loop():
    log("Engine loop started.")
    while True:
        try:
            prepare_day_if_needed()
            with engine_lock:
                prepared = engine_state.get("prepared", False)
            if prepared:
                start_websocket_if_needed()
                check_exits()
        except Exception as e:
            log(f"engine_loop error: {e}")
        time.sleep(INTERVAL_SECS)

# ----------------------------------------------------------
# FLASK ROUTES
# ----------------------------------------------------------
@app.route("/", methods=["GET"])
def root():
    return "RajanTradeAutomation Engine ✔", 200

@app.route("/health", methods=["GET"])
def health():
    with engine_lock:
        data = {
            "ok": True,
            "time": now_ist().isoformat(),
            "prepared": engine_state.get("prepared", False),
            "bias": engine_state.get("bias"),
            "symbols": engine_state.get("selected_symbols", []),
            "sectors": engine_state.get("selected_sectors", [])
        }
    return jsonify(data)

@app.route("/ping", methods=["GET"])
def ping():
    log("Ping received.")
    return "PONG", 200

@app.route("/reload-settings", methods=["POST"])
def reload_settings():
    s = fetch_settings_from_sheet()
    with engine_lock:
        engine_state["settings"] = s
    return jsonify({"ok": True, "settings": s})

# ----------------------------------------------------------
# MAIN
# ----------------------------------------------------------
if __name__ == "__main__":
    threading.Thread(target=engine_loop, daemon=True).start()
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
