# ==========================================================
# RajanTradeAutomation – main.py (NEW STRATEGY LIVE ENGINE)
# Version: 1.0
# Engine: Fyers REST + Fyers WebSocket + Google Sheets WebApp
# Strategy: Market breadth -> Sector -> FnO stocks -> Lowest Volume 5m
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
# ENVIRONMENT (Render dashboard मध्ये आधीच सेट केलेले)
# ----------------------------------------------------------
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY", "").strip()
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
INTERVAL_SECS = int(os.getenv("INTERVAL_SECS", "60"))   # heartbeat / engine loop

IST = ZoneInfo("Asia/Kolkata")

# ----------------------------------------------------------
# GLOBAL STATE
# ----------------------------------------------------------
app = Flask(__name__)

# Fyers REST client (quotes, history etc.)
fyers_rest = fyersModel.FyersModel(
    client_id=FYERS_CLIENT_ID,
    token=FYERS_ACCESS_TOKEN,
    log_path=""
)

# Engine state
engine_state = {
    "day": None,              # "YYYY-MM-DD"
    "bias": None,             # "BUY" / "SELL"
    "selected_sectors": [],   # ["NIFTY BANK", "NIFTY PSU BANK", ...]
    "selected_symbols": [],   # ["NSE:SBIN-EQ", ...]
    "symbols_direction": {},  # {"NSE:SBIN-EQ": "BUY", ...}
    "prepared": False,
    "ws_started": False,
    "settings": {},

    # per symbol candle & trade state
    "symbols": {
        # "NSE:SBIN-EQ": {
        #   "candles": [ {time, o, h, l, c, v, index}, ... ],
        #   "lowest_volume_so_far": 0,
        #   "signal_found": False,
        #   "signal_candle": {...},
        #   "active_trade": None
        # }
    }
}

engine_lock = threading.Lock()  # to protect engine_state

# ----------------------------------------------------------
# UTILITIES
# ----------------------------------------------------------
def now_ist():
    return datetime.now(tz=IST)

def today_str():
    return now_ist().strftime("%Y-%m-%d")

def ist_time_hhmm():
    return now_ist().strftime("%H:%M")

def log(msg):
    print(f"[{now_ist().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def post_webapp(action: str, payload: dict):
    """Call Google Apps Script WebApp with JSON {action, payload}."""
    if not WEBAPP_URL:
        log("WEBAPP_URL missing, cannot post.")
        return None
    try:
        body = {"action": action, "payload": payload}
        resp = requests.post(WEBAPP_URL, json=body, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        else:
            log(f"WebApp {action} error: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        log(f"WebApp {action} exception: {e}")
    return None

def fetch_settings_from_sheet():
    """Ask WebApp for current Settings."""
    res = post_webapp("getSettings", {})
    if res and res.get("ok"):
        return res.get("settings", {})
    return {}

# ----------------------------------------------------------
# DATA FETCHERS  (NSE / FYERS REST)
# ----------------------------------------------------------

def fetch_market_breadth():
    """
    TODO: Replace with actual NSE / Fyers breadth API.
    Expected to return (advances, declines).
    """
    try:
        # Example (pseudo):
        # resp = requests.get("https://some-nse-api/adv-dec", timeout=5)
        # data = resp.json()
        # adv = data["advances"]
        # dec = data["declines"]
        # return adv, dec
        log("fetch_market_breadth() – TODO: wire real API. Using dummy 25/25 for now.")
        return 25, 25
    except Exception as e:
        log(f"fetch_market_breadth error: {e}")
        return 0, 0

def fetch_sector_performance():
    """
    TODO: Implement NSE sector indices fetch.
    Must return list of {sector_name, sector_code, per_chg, advances, declines}
    """
    sectors = []
    try:
        # Example pseudo-call:
        # url = "https://www.nseindia.com/api/allIndices"
        # resp = requests.get(url, headers=..., timeout=10)
        # data = resp.json()["data"]
        # For each index we care about, map name -> %change
        log("fetch_sector_performance() – TODO: real NSE API. Returning empty list for now.")
    except Exception as e:
        log(f"fetch_sector_performance error: {e}")
    return sectors

def fyers_symbol(symbol: str) -> str:
    """Ensure symbol in Fyers format e.g. 'NSE:SBIN-EQ'."""
    s = symbol.strip().upper()
    if ":" not in s:
        s = "NSE:" + s
    if not s.endswith("-EQ"):
        s = s + "-EQ"
    return s

def fetch_fno_universe():
    """
    TODO: Implement FnO universe fetch + sector mapping.
    For now, returns empty list.
    Each row: {"symbol": "NSE:SBIN-EQ", "name": "...", "sector": "NIFTY BANK", "is_fno": True}
    """
    log("fetch_fno_universe() – TODO: implement NSE FnO + sector mapping.")
    return []

def fyers_quotes(symbols):
    """
    Fetch LTP, %change, volume for given symbols from Fyers REST.
    """
    if not symbols:
        return {}
    try:
        symbol_str = ",".join(symbols)
        data = {
            "symbols": symbol_str
        }
        resp = fyers_rest.quotes(data=data)
        q = {}
        for item in resp.get("d", []):
            sym = item.get("n")  # symbol name
            q[sym] = {
                "ltp": item.get("v", {}).get("lp", 0),
                "percent_change": item.get("v", {}).get("chp", 0),
                "volume": item.get("v", {}).get("volume", 0)
            }
        return q
    except Exception as e:
        log(f"fyers_quotes error: {e}")
        return {}

def fyers_5min_history(symbol, start: datetime, end: datetime):
    """
    Fetch 5-min candles for given symbol between start and end (IST).
    Returns list of dicts: {time, open, high, low, close, volume}
    """
    try:
        # Fyers uses epoch seconds in IST for 'from' and 'to'
        start_epoch = int(start.timestamp())
        end_epoch = int(end.timestamp())

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
            # filter within required time
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
# STOCK SELECTION ENGINE (09:25–09:29)
# ----------------------------------------------------------

def decide_bias(adv, dec):
    if adv > dec:
        return "BUY"
    elif dec > adv:
        return "SELL"
    return None  # no clear bias

def pick_sectors(bias, sectors, settings):
    """
    sectors: list of {sector_name, sector_code, per_chg, advances, declines}
    BUY -> pick top +ve ; SELL -> bottom -ve
    """
    if not sectors:
        return []

    if bias == "BUY":
        sorted_sec = sorted(sectors, key=lambda x: x.get("per_chg", 0), reverse=True)
        count = int(settings.get("BUY_SECTOR_COUNT", 2))
    elif bias == "SELL":
        sorted_sec = sorted(sectors, key=lambda x: x.get("per_chg", 0))
        count = int(settings.get("SELL_SECTOR_COUNT", 2))
    else:
        return []

    return sorted_sec[:count]

def filter_stocks_by_percent(bias, universe_rows, quotes_map, settings):
    """
    universe_rows: [{symbol, name, sector, is_fno, enabled}]
    quotes_map: {symbol: {ltp, percent_change, volume}}
    """
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
            if 0 <= pc <= max_up:
                selected.append((sym, row["sector"], pc, q))
        elif bias == "SELL":
            if max_down <= pc <= 0:
                selected.append((sym, row["sector"], pc, q))

    # Rank by %change absolute in correct direction
    if bias == "BUY":
        selected.sort(key=lambda x: x[2], reverse=True)
    else:
        selected.sort(key=lambda x: x[2])  # more negative first

    # we can limit to e.g. 5–10 stocks
    max_stocks = 10
    return selected[:max_stocks]

def prepare_day_if_needed():
    with engine_lock:
        today = today_str()
        if engine_state["day"] == today and engine_state["prepared"]:
            return  # already done

    # Only run between 09:25 and 09:29 IST
    now = now_ist()
    hhmm = now.strftime("%H:%M")
    if not ("09:25" <= hhmm < "09:30"):
        return

    log("Preparing day – fetching settings, breadth, sector performance, FnO universe...")

    settings = fetch_settings_from_sheet()
    adv, dec = fetch_market_breadth()
    bias = decide_bias(adv, dec)

    sectors = fetch_sector_performance()
    chosen_sectors = pick_sectors(bias, sectors, settings)

    # Universe & filter by chosen sectors
    universe = fetch_fno_universe()
    chosen_symbols = [u for u in universe if u.get("sector") in [s["sector_name"] for s in chosen_sectors]]

    # Make Fyers symbols
    for u in chosen_symbols:
        u["symbol"] = fyers_symbol(u["symbol"])

    # Quotes for chosen symbols
    quotes_map = fyers_quotes([u["symbol"] for u in chosen_symbols])

    # Filter by %change rule
    filtered = filter_stocks_by_percent(bias, chosen_symbols, quotes_map, settings)

    # Final selection
    final_symbols = [row[0] for row in filtered]
    symbols_direction = {sym: bias for sym in final_symbols}

    # Push to StockList sheet
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

    # Also sync Universe sheet
    post_webapp("syncUniverse", {"universe": universe})
    post_webapp("updateSectorPerf", {"sectors": sectors})

    # Fill first 3 candles (9:15–9:30) via history
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
        engine_state["selected_sectors"] = [s["sector_name"] for s in chosen_sectors]
        engine_state["selected_symbols"] = final_symbols
        engine_state["symbols_direction"] = symbols_direction
        engine_state["symbols"] = symbol_states
        engine_state["settings"] = settings
        engine_state["prepared"] = True

    log(f"Day prepared. Bias={bias}, symbols={final_symbols}")

# ----------------------------------------------------------
# FYERS WEBSOCKET HANDLERS (EXECUTIVE PATTERN)
# ----------------------------------------------------------

fyers_ws = None

def onmessage_ws(message):
    """
    Called for every incoming WebSocket message.
    We expect SymbolUpdate ticks.
    """
    # message example: {'symbol': 'NSE:SBIN-EQ', 'ltp': 620.5, 'tt': 1701675900, ...}
    try:
        if isinstance(message, str):
            msg = json.loads(message)
        else:
            msg = message
    except Exception:
        msg = message

    # Fyers sends key "symbol" and "ltp" etc.
    symbol = msg.get("symbol")
    if not symbol:
        return

    ltp = msg.get("ltp") or msg.get("last_traded_price") or msg.get("price")
    ts = msg.get("timestamp") or msg.get("tt") or int(time.time())
    t = datetime.fromtimestamp(ts, tz=IST)

    handle_tick(symbol, float(ltp or 0), t)

def onerror_ws(message):
    log(f"[WS ERROR] {message}")

def onclose_ws(message):
    log(f"[WS CLOSED] {message}")

def onopen_ws():
    """
    Subscribe to selected symbols with SymbolUpdate type.
    """
    global fyers_ws
    with engine_lock:
        symbols = engine_state.get("selected_symbols", [])
    if not symbols:
        log("WS onopen: no symbols to subscribe.")
        return

    data_type = "SymbolUpdate"
    log(f"WS onopen: subscribing to {symbols}")
    fyers_ws.subscribe(symbols=symbols, data_type=data_type)
    fyers_ws.keep_running()

def start_websocket_if_needed():
    global fyers_ws
    with engine_lock:
        symbols = engine_state.get("selected_symbols", [])
        ws_started = engine_state.get("ws_started", False)

    if ws_started or not symbols:
        return

    log("Starting Fyers WebSocket for live ticks...")
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
# TICK HANDLING -> 5m CANDLES + SIGNAL / ENTRY / EXIT
# ----------------------------------------------------------

def candle_bucket_time(t: datetime) -> datetime:
    """
    Given tick time, return candle close time for 5-min candle.
    """
    minute = (t.minute // 5) * 5 + 5
    hour = t.hour
    if minute >= 60:
        minute -= 60
        hour += 1
    return t.replace(hour=hour, minute=minute, second=0, microsecond=0)

def handle_tick(symbol: str, ltp: float, t: datetime):
    with engine_lock:
        sym_state = engine_state["symbols"].get(symbol)
        if not sym_state:
            return
        bias = engine_state["bias"]
        settings = engine_state["settings"]

    # Build / update current 5-min candle
    bucket_time = candle_bucket_time(t)

    candles = sym_state["candles"]
    if candles and candles[-1]["time"] == bucket_time.isoformat():
        # update current candle
        c = candles[-1]
        c["high"] = max(c["high"], ltp)
        c["low"] = min(c["low"], ltp)
        c["close"] = ltp
        c["volume"] += 1  # simplistic tick-volume; you can replace with real volume from msg
    else:
        # close previous candle (if any) and create new one
        index = (candles[-1]["candle_index"] + 1) if candles else 1
        c = {
            "symbol": symbol,
            "time": bucket_time.isoformat(),
            "timeframe": "5m",
            "open": ltp,
            "high": ltp,
            "low": ltp,
            "close": ltp,
            "volume": 1,
            "candle_index": index,
            "lowest_volume_so_far": sym_state.get("lowest_volume_so_far") or 0,
            "is_signal": False,
            "direction": bias
        }
        candles.append(c)

    # recompute lowest volume so far & check signal only when candle closes
    # approx: when now > bucket_time
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

    # we care only from 4th candle onwards
    if idx < 4:
        return

    if lowest_vol == 0 or vol < lowest_vol:
        lowest_vol = vol

    # update lowest volume in state
    c["lowest_volume_so_far"] = lowest_vol

    # Check signal conditions
    is_signal = False
    direction = None

    if bias == "BUY":
        # red candle (open > close) & lowest volume
        if o > cl and vol <= lowest_vol:
            is_signal = True
            direction = "BUY"
    elif bias == "SELL":
        # green candle (close > open) & lowest volume
        if cl > o and vol <= lowest_vol:
            is_signal = True
            direction = "SELL"

    if not is_signal:
        with engine_lock:
            sym_state["lowest_volume_so_far"] = lowest_vol
        return

    # Mark signal in memory & sheet
    entry_price = h if direction == "BUY" else l
    sl = l if direction == "BUY" else h
    risk_per_share = abs(entry_price - sl)

    rr = float(settings.get("RR_RATIO", 2.0) or 2.0)
    target_price = entry_price + rr * risk_per_share if direction == "BUY" else entry_price - rr * risk_per_share

    # Quantity from per-trade risk
    qty = 1
    per_trade_risk_en = str(settings.get("ENABLE_PER_TRADE_RISK", "TRUE")).upper() == "TRUE"
    if per_trade_risk_en:
        per_trade_risk = float(settings.get("PER_TRADE_RISK", 1000) or 1000.0)
        if risk_per_share > 0:
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

    # Immediately treat entry as triggered at candle high/low (simplification)
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

    # update in memory
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

    log(f"Signal & entry created for {symbol} dir={direction} entry={entry_price} sl={sl} tgt={target_price} qty={qty}")

# ----------------------------------------------------------
# EXIT ENGINE – TARGET (half) + 15:15 square-off
# ----------------------------------------------------------

def check_exits():
    """Check for SL/Target/Time exits using latest LTP from quotes."""
    with engine_lock:
        symbols_with_trades = [s for s, st in engine_state["symbols"].items() if st.get("active_trade")]

    if not symbols_with_trades:
        return

    quotes = fyers_quotes(symbols_with_trades)
    settings = engine_state["settings"]
    partial_percent = float(settings.get("PARTIAL_EXIT_PERCENT", 50) or 50.0)

    for sym in symbols_with_trades:
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

        now = now_ist()
        auto_sq_time = engine_state["settings"].get("AUTO_SQUAREOFF_TIME", "15:15")
        auto_h, auto_m = [int(x) for x in auto_sq_time.split(":")]
        auto_sq_dt = now.replace(hour=auto_h, minute=auto_m, second=0, microsecond=0)

        exit_events = []

        # 1) SL check
        if direction == "BUY" and ltp <= sl and not full_done:
            pnl = (sl - entry) * qty_total
            exit_events.append(("SL", qty_rem, sl, "SL-HIT", pnl))
        elif direction == "SELL" and ltp >= sl and not full_done:
            pnl = (entry - sl) * qty_total
            exit_events.append(("SL", qty_rem, sl, "SL-HIT", pnl))

        # 2) Target / partial exit
        if not half_done and not full_done:
            if direction == "BUY" and ltp >= tgt:
                qty_half = int(qty_total * (partial_percent / 100.0))
                if qty_half <= 0:
                    qty_half = qty_total
                pnl = (tgt - entry) * qty_half
                exit_events.append(("PARTIAL", qty_half, tgt, "PARTIAL", pnl))
            elif direction == "SELL" and ltp <= tgt:
                qty_half = int(qty_total * (partial_percent / 100.0))
                if qty_half <= 0:
                    qty_half = qty_total
                pnl = (entry - tgt) * qty_half
                exit_events.append(("PARTIAL", qty_half, tgt, "PARTIAL", pnl))

        # 3) Time-based 15:15 square-off
        if now >= auto_sq_dt and not full_done:
            pnl = (ltp - entry) * qty_rem if direction == "BUY" else (entry - ltp) * qty_rem
            exit_events.append(("FINAL", qty_rem, ltp, "CLOSED", pnl))

        for exit_type, exit_qty, exit_price, status, pnl in exit_events:
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
            log(f"Exit {exit_type} for {sym}, qty={exit_qty}, price={exit_price}, pnl={pnl}")

            with engine_lock:
                if exit_type == "PARTIAL":
                    trade["qty_remaining"] -= exit_qty
                    trade["half_exit_done"] = True
                    if trade["qty_remaining"] <= 0:
                        trade["full_exit_done"] = True
                else:  # SL or FINAL
                    trade["qty_remaining"] = 0
                    trade["half_exit_done"] = True
                    trade["full_exit_done"] = True
                st["active_trade"] = trade
                engine_state["symbols"][sym] = st

# ----------------------------------------------------------
# ENGINE HEARTBEAT LOOP  (uses INTERVAL_SECS)
# ----------------------------------------------------------

def engine_loop():
    log("Engine loop started.")
    while True:
        try:
            # 1) Prepare day between 09:25–09:29
            prepare_day_if_needed()

            # 2) Start WS once selection done
            with engine_lock:
                prepared = engine_state["prepared"]
            if prepared:
                start_websocket_if_needed()

            # 3) Periodic exit checks
            check_exits()

        except Exception as e:
            log(f"Engine loop error: {e}")

        time.sleep(INTERVAL_SECS)

# ----------------------------------------------------------
# FLASK ROUTES (Ping / Health / Manual control)
# ----------------------------------------------------------

@app.route("/", methods=["GET"])
def root():
    return "RajanTradeAutomation Engine Running ✔", 200

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "time": now_ist().isoformat(),
        "prepared": engine_state.get("prepared", False),
        "bias": engine_state.get("bias"),
        "symbols": engine_state.get("selected_symbols", [])
    })

@app.route("/ping", methods=["GET"])
def ping():
    # For UptimeRobot external ping
    log("Ping received.")
    return "PONG", 200

@app.route("/reload-settings", methods=["POST"])
def reload_settings():
    s = fetch_settings_from_sheet()
    with engine_lock:
        engine_state["settings"] = s
    return jsonify({"ok": True, "settings": s})

# ----------------------------------------------------------
# MAIN ENTRY
# ----------------------------------------------------------

if __name__ == "__main__":
    # Start engine loop in background
    threading.Thread(target=engine_loop, daemon=True).start()

    # Run Flask app (Render will bind PORT env automatically)
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
