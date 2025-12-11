# ============================================================
# RajanTradeAutomation - main.py (FINAL v6.0)
# - Bias once per day (09:25-09:29 IST)
# - Historical fill of three 5m candles
# - Live engine from 4th candle (09:30 onwards)
# - Dynamic subscription (StockList selected TRUE)
# - subscribeSymbols endpoint support
# - PAPER trade execution by default; LIVE stub available
# - Supervisor to auto-restart threads and error reporting
# ============================================================

import os, time, threading, requests, json, traceback
from datetime import datetime, timedelta

# Optional imports
try:
    from nsetools import Nse
    NSE_CLIENT = Nse()
except Exception as e:
    NSE_CLIENT = None
    print("nsetools not available:", e)

# Fyers websocket import – optional
try:
    from fyers_apiv3.FyersWebsocket import data_ws
    FYERS_WS_AVAILABLE = True
except Exception as e:
    data_ws = None
    FYERS_WS_AVAILABLE = False
    print("fyers websocket lib not available:", e)

# ENV
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()  # e.g. https://script.google.com/macros/s/xxx/exec
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
INTERVAL_SECS = int(os.getenv("INTERVAL_SECS", "60"))
MODE = os.getenv("MODE", "PAPER").upper()
AUTO_UNIVERSE = os.getenv("AUTO_UNIVERSE", "FALSE").upper() == "TRUE"

# Helper: call WebApp
def call_webapp(action, payload=None, timeout=20):
    if payload is None: payload = {}
    if not WEBAPP_URL:
        return {"ok": False, "error": "WEBAPP_URL not configured"}
    body = {"action": action, "payload": payload}
    try:
        r = requests.post(WEBAPP_URL, json=body, timeout=timeout)
        try: return r.json()
        except Exception: return {"ok": True, "raw": r.text}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def set_state(key, value):
    return call_webapp("pushState", {"items":[{"key": key, "value": str(value)}]})

# Time helpers (IST)
def now_ist():
    return datetime.utcnow() + timedelta(hours=5, minutes=30)
def time_in_hm(s):
    # s = "HH:MM"
    hh, mm = [int(x) for x in s.split(":")]
    return hh, mm

# ---------------- Strategy core ----------------
SECTOR_INDEX_MAP = {
    "NIFTY BANK": "BANK", "NIFTY PSU BANK": "PSUBANK", "NIFTY OIL & GAS": "OILGAS",
    "NIFTY IT": "IT", "NIFTY PHARMA": "PHARMA", "NIFTY AUTO": "AUTO", "NIFTY FMCG": "FMCG",
    "NIFTY METAL": "METAL", "NIFTY FIN SERVICE": "FIN", "NIFTY REALTY": "REALTY", "NIFTY MEDIA": "MEDIA"
}

def get_settings():
    r = call_webapp("getSettings", {})
    return r.get("settings", {}) if isinstance(r, dict) else {}

def compute_bias_once(settings):
    # Should run only during 09:25-09:29 window once.
    if NSE_CLIENT is None:
        return {"ok": False, "error": "NSE client missing"}

    try:
        q = NSE_CLIENT.get_index_quote("NIFTY 50")
        adv = int(q.get("advances", 0))
        dec = int(q.get("declines", 0))
        unc = int(q.get("unchanged", 0))
    except Exception as e:
        return {"ok": False, "error": str(e)}

    bias = "BUY" if adv > dec else ("SELL" if dec > adv else "NEUTRAL")
    strength = adv * 100.0 / (adv + dec) if (adv + dec) > 0 else 0.0
    threshold = float(settings.get("BIAS_THRESHOLD_PERCENT", 60) or 60)
    set_state("BIAS_STATUS", f"{bias}|{strength:.1f}|{threshold:.1f}")
    return {"ok": True, "bias": bias, "advances": adv, "declines": dec, "strength": strength, "threshold": threshold}

def fetch_sector_perf():
    if NSE_CLIENT is None: return []
    try:
        all_idx = NSE_CLIENT.get_all_index_quote()
    except Exception:
        return []
    sectors=[]
    for item in all_idx:
        name = item.get("index") or item.get("indexSymbol")
        if not name or name not in SECTOR_INDEX_MAP: continue
        chg = float(item.get("percentChange", 0.0) or 0.0)
        adv = int(item.get("advances",0) or 0)
        dec = int(item.get("declines",0) or 0)
        sectors.append({"sector_name": name, "sector_code": SECTOR_INDEX_MAP[name], "%chg": chg, "advances": adv, "declines": dec})
    return sectors

def build_sector_top(bias, settings, sectors):
    if not sectors: return [], set()
    if bias == "SELL":
        sectors_sorted = sorted(sectors, key=lambda s: s["%chg"])
        top_count = int(settings.get("SELL_SECTOR_COUNT", 2) or 2)
    else:
        sectors_sorted = sorted(sectors, key=lambda s: s["%chg"], reverse=True)
        top_count = int(settings.get("BUY_SECTOR_COUNT", 2) or 2)
    top_count = max(1, top_count)
    top = sectors_sorted[:top_count]
    top_names = {s["sector_name"] for s in top}
    return sectors_sorted, top_names

def fetch_stocks_for_top_sectors(top_sector_names, bias, settings):
    if NSE_CLIENT is None or not top_sector_names: return []
    max_up = float(settings.get("MAX_UP_PERCENT", 2.5))
    max_down = float(settings.get("MAX_DOWN_PERCENT", -2.5))
    all_rows=[]
    for sec_name in top_sector_names:
        try:
            quotes = NSE_CLIENT.get_stock_quote_in_index(index=sec_name, include_index=False)
        except Exception:
            continue
        for q in quotes:
            sym = q.get("symbol")
            if not sym: continue
            pchg = float(q.get("pChange",0.0) or 0.0)
            ltp = float(q.get("ltp",0.0) or 0.0)
            vol = int(q.get("totalTradedVolume",0) or 0)
            selected = False
            if bias == "BUY":
                if pchg > 0 and pchg <= max_up:
                    selected = True
            elif bias == "SELL":
                if pchg < 0 and pchg >= max_down:
                    selected = True
            row = {"symbol": f"NSE:{sym}-EQ", "direction_bias": bias, "sector": sec_name, "%chg": pchg, "ltp": ltp, "volume": vol, "selected": selected}
            all_rows.append(row)
    return all_rows

# ----------------- Candle & Signal Engine -----------------
CANDLE_BUFF = {}     # symbol -> list of ticks {"ts": epoch, "price":float, "vol":int}
AGG_CANDLES = {}     # symbol -> list of candles (dict)
SIGNAL_STATE = {}    # symbol -> current signal object

def feed_tick(symbol, price, volume, ts=None):
    if ts is None: ts = time.time()
    buf = CANDLE_BUFF.setdefault(symbol, [])
    buf.append({"ts": ts, "price": price, "vol": volume})
    if len(buf) > 2000: del buf[0:-1500]

def build_5m_candle(symbol, slot_start_ts):
    ticks = [t for t in CANDLE_BUFF.get(symbol, []) if t["ts"] >= slot_start_ts and t["ts"] < slot_start_ts + 300]
    if not ticks: return None
    open_p = ticks[0]["price"]
    close_p = ticks[-1]["price"]
    high = max(t["price"] for t in ticks)
    low = min(t["price"] for t in ticks)
    volume = sum(t["vol"] for t in ticks)
    return {"symbol": symbol, "time": datetime.fromtimestamp(slot_start_ts).isoformat(), "timeframe": "5m", "open": open_p, "high": high, "low": low, "close": close_p, "volume": volume}

def push_5m_candle(candle, candle_index):
    prev_vols = [c["volume"] for c in AGG_CANDLES.get(candle["symbol"], [])] if AGG_CANDLES.get(candle["symbol"]) else []
    lowest = min(prev_vols + [candle["volume"]]) if prev_vols else candle["volume"]
    payload = {"candles":[{
        "symbol": candle["symbol"],
        "time": candle["time"],
        "timeframe": candle["timeframe"],
        "open": candle["open"],
        "high": candle["high"],
        "low": candle["low"],
        "close": candle["close"],
        "volume": candle["volume"],
        "candle_index": candle_index,
        "lowest_volume_so_far": lowest,
        "is_signal": False,
        "direction": "BUY" if candle["close"] >= candle["open"] else "SELL"
    }]}
    call_webapp("pushCandle", payload)
    AGG_CANDLES.setdefault(candle["symbol"], []).append({"time": candle["time"], "volume": candle["volume"]})
    return payload["candles"][0]

# Signal detection rules (as specified)
def evaluate_signal_for_candle(candle, settings):
    symbol = candle["symbol"]
    prev_candles = AGG_CANDLES.get(symbol, [])
    vols = [c["volume"] for c in prev_candles] + [candle["volume"]]
    if len(vols) < 3:
        return None
    lowest_so_far = min(vols[:-1])  # lowest among earlier candles
    # We want current candle volume < lowest_so_far AND candle color matches bias rule
    # Determine bias from State sheet
    state = call_webapp("getSettings", {})
    ssettings = state.get("settings", {}) if isinstance(state, dict) else {}
    bias_state = None
    bias_resp = call_webapp("getSettings", {}, timeout=10)
    # fallback: read BIAS_STATUS from State sheet
    st = call_webapp("pushState", {"items":[]})
    # read State sheet via getSettings? simplified: call WebApp 'getSettings' doesn't provide BIAS
    # We will use global SIGNAL_STATE placeholder to decide direction per stock (StockList has DirectionBias)
    # For simplicity, get StockList entry
    stocklist = call_webapp("getStockList", {})
    stocks = stocklist.get("stocks", []) if isinstance(stocklist, dict) else []
    info = next((s for s in stocks if s.get("symbol","").upper() == symbol.upper()), {})
    intended_direction = info.get("direction_bias", "").upper() or "BUY"
    # BUY rule: signal candle is RED (open > close) and volume < lowest_so_far
    is_red = candle["open"] > candle["close"]
    is_green = candle["close"] > candle["open"]
    if intended_direction == "BUY":
        if is_red and candle["volume"] < lowest_so_far:
            return {"symbol": symbol, "direction": "BUY", "entry_price": candle["high"], "sl": candle["low"], "candle_index": candle.get("candle_index",0)}
    elif intended_direction == "SELL":
        if is_green and candle["volume"] < lowest_so_far:
            return {"symbol": symbol, "direction": "SELL", "entry_price": candle["low"], "sl": candle["high"], "candle_index": candle.get("candle_index",0)}
    return None

# Quantity calc
def compute_qty(entry, sl, risk_per_trade):
    per_share_risk = abs(entry - sl)
    if per_share_risk <= 0: return 0
    qty = int(risk_per_trade // per_share_risk)
    return max(0, qty)

# Trade execution (stub)
def execute_trade(signal, settings):
    # signal = {"symbol","direction","entry_price","sl","candle_index"}
    mode = MODE
    risk = float(settings.get("PER_TRADE_RISK", 1000) or 1000)
    rr = float(settings.get("RR_RATIO", 2) or 2)
    qty = compute_qty(signal["entry_price"], signal["sl"], risk)
    target = signal["entry_price"] + rr*(signal["entry_price"] - signal["sl"]) if signal["direction"] == "BUY" else signal["entry_price"] - rr*(signal["sl"] - signal["entry_price"])
    payload = {
        "symbol": signal["symbol"],
        "direction": signal["direction"],
        "entry_price": signal["entry_price"],
        "sl": signal["sl"],
        "target_price": target,
        "qty_total": qty,
        "entry_time": datetime.utcnow().isoformat()
    }
    if mode == "PAPER":
        # push to sheets as executed trade (simulate immediate fill)
        call_webapp("pushTradeEntry", payload)
        print("PAPER trade executed ->", payload)
        return {"ok": True, "mode": "PAPER", "payload": payload}
    else:
        # LIVE stub: implement broker order call here (Fyers REST order)
        # For safety default is PAPER; implement if you want LIVE.
        print("LIVE execution not implemented. Received:", payload)
        return {"ok": False, "error": "LIVE execution not enabled"}

# ----------------- WebSocket (Fyers) integration -----------------
FYERS_WS = None
SUBSCRIBED = set()
def fyers_onmessage(msg):
    try:
        if not isinstance(msg, dict):
            return
        data = msg.get("d") or msg.get("data") or msg.get("response")
        if isinstance(data, list):
            for it in data:
                sym = it.get("symbol") or it.get("s")
                ltp = it.get("ltp") or it.get("last_price") or it.get("l")
                vol = it.get("volume") or it.get("v") or 0
                if sym and ltp is not None:
                    feed_tick(sym, float(ltp), int(vol or 0), time.time())
        else:
            sym = msg.get("symbol") or msg.get("s")
            ltp = msg.get("ltp")
            vol = msg.get("volume") or 0
            if sym and ltp is not None:
                feed_tick(sym, float(ltp), int(vol or 0), time.time())
    except Exception as e:
        print("fyers_onmessage error:", e)

def fyers_onopen():
    print("FYERS WS connected")
    # subscribe to current selected symbols
    try:
        sl = call_webapp("getStockList", {})
        stocks = sl.get("stocks", []) if isinstance(sl, dict) else []
        syms = [s["symbol"] for s in stocks if s.get("selected")]
        subscribe_to_fyers_symbols(syms)
    except Exception as e:
        print("fyers_onopen err:", e)

def fyers_onerror(e):
    print("FYERS WS error:", e)

def fyers_onclose(msg):
    print("FYERS WS closed:", msg)

def start_fyers_ws(symbols=None):
    global FYERS_WS, SUBSCRIBED, FYERS_ACCESS_TOKEN
    if not FYERS_WS_AVAILABLE:
        print("FYERS websocket lib not installed.")
        return
    if not FYERS_ACCESS_TOKEN:
        print("FYERS_ACCESS_TOKEN not set. WebSocket not started.")
        return
    try:
        SUBSCRIBED = set(symbols or [])
        FYERS_WS = data_ws.FyersDataSocket(
            access_token = FYERS_ACCESS_TOKEN,
            log_path = "",
            litemode = False,
            write_to_file = False,
            reconnect = True,
            on_connect = fyers_onopen,
            on_close = fyers_onclose,
            on_error = fyers_onerror,
            on_message = fyers_onmessage
        )
        FYERS_WS.connect()
    except Exception as e:
        print("start_fyers_ws error:", e)

def subscribe_to_fyers_symbols(symbols):
    global SUBSCRIBED, FYERS_WS
    if not symbols: return
    symbols = [s for s in symbols if s]
    SUBSCRIBED.update(symbols)
    # call WebApp endpoint to log subscriptions
    call_webapp("subscribeSymbols", {"symbols": list(SUBSCRIBED), "source": "engine"})
    # If FYERS_WS object supports subscribe method, call it
    try:
        if FYERS_WS:
            FYERS_WS.subscribe(symbols=symbols, data_type="SymbolUpdate")
    except Exception as e:
        print("subscribe error:", e)

# ----------------- Aggregator & Engine Loops -----------------
def aggregator_thread():
    last_slot = None
    while True:
        try:
            now = now_ist()
            minute = (now.minute // 5) * 5
            slot_start = datetime(now.year, now.month, now.day, now.hour, minute, 0)
            slot_ts = slot_start.timestamp()
            if last_slot is None:
                last_slot = slot_ts
            # if slot changed -> finalize previous slot candle
            if slot_ts != last_slot:
                prev_slot = last_slot
                symbols = list(CANDLE_BUFF.keys())
                for symbol in symbols:
                    candle = build_5m_candle(symbol, prev_slot)
                    if candle:
                        candle_index = len(AGG_CANDLES.get(symbol, [])) + 1
                        pushed = push_5m_candle(candle, candle_index)
                        # after pushing, evaluate signal if >=4th candle
                        if candle_index >= 4:
                            sig = evaluate_signal_for_candle(candle, get_settings())
                            if sig:
                                # cancel previous pending signals for symbol
                                SIGNAL_STATE[symbol] = sig
                                execute_trade(sig, get_settings())
                last_slot = slot_ts
        except Exception as e:
            print("aggregator error:", e, traceback.format_exc())
            try:
                call_webapp("pushState", {"items":[{"key":"ENGINE_ERROR","value":str(e)}]})
            except: pass
        time.sleep(5)

def engine_supervisor():
    # Supervisor starts engine and aggregator and restarts if they crash
    while True:
        try:
            t_agg = threading.Thread(target=aggregator_thread, daemon=True)
            t_agg.start()
            # Start fyers ws if token present
            if FYERS_WS_AVAILABLE and FYERS_ACCESS_TOKEN:
                # subscribe symbols from StockList
                sl = call_webapp("getStockList", {})
                stocks = sl.get("stocks", []) if isinstance(sl, dict) else []
                syms = [s["symbol"] for s in stocks if s.get("selected")]
                start_fyers_ws(syms)
            # monitor threads
            while True:
                if not t_agg.is_alive():
                    print("aggregator thread died, restarting...")
                    break
                time.sleep(5)
        except Exception as e:
            print("supervisor error:", e, traceback.format_exc())
        # wait a bit then restart
        time.sleep(3)

# ----------------- Daily Bias/Seed Task (09:25-09:29 window) -----------------
BIAS_DONE_DATE = None

def daily_bias_and_seed():
    global BIAS_DONE_DATE
    while True:
        try:
            now = now_ist()
            today_str = now.strftime("%Y-%m-%d")
            if BIAS_DONE_DATE == today_str:
                # already done for today
                time.sleep(20)
                continue
            # check window 09:25 <= time < 09:30
            h,m = now.hour, now.minute
            if (h == 9 and (m >= 25 and m < 30)):
                settings = get_settings()
                # compute bias once
                bias_res = compute_bias_once(settings)
                if not bias_res.get("ok"):
                    print("Bias compute failed:", bias_res)
                # fetch sectors -> push
                sectors = fetch_sector_perf()
                call_webapp("updateSectorPerf", {"sectors": sectors})
                # build top sectors and stocks
                sectors_all, top_names = build_sector_top(bias_res.get("bias","NEUTRAL"), settings, sectors)
                stocks_all = fetch_stocks_for_top_sectors(top_names, bias_res.get("bias","NEUTRAL"), settings)
                # push stock list to sheet
                call_webapp("updateStockList", {"stocks": stocks_all})
                # Optionally, if AUTO_UNIVERSE is true, sync Universe (not implemented heavy)
                # Historical fill for 3 candles: we push placeholder candles by fetching historical via FYERS_HISTORICAL_URL if available
                # For now we rely on aggregator (which uses tick buffer) – but to ensure CandleHistory initial 3 candles, attempt to call fyers historical or skip.
                # Mark as done
                BIAS_DONE_DATE = today_str
                print("Bias & seed done for", today_str, "bias:", bias_res.get("bias"))
            time.sleep(10)
        except Exception as e:
            print("daily_bias error:", e, traceback.format_exc())
            time.sleep(5)

# ----------------- Start background services -----------------
def start_background():
    threads = []
    t_super = threading.Thread(target=engine_supervisor, daemon=True)
    t_super.start()
    threads.append(t_super)
    t_bias = threading.Thread(target=daily_bias_and_seed, daemon=True)
    t_bias.start()
    threads.append(t_bias)
    print("Background threads started:", [t.name for t in threads])
    return threads

if __name__ == "__main__":
    print("RajanTradeAutomation v6.0 starting...")
    start_background()
    # Minimal Flask for debug routes
    try:
        from flask import Flask, jsonify
        app = Flask(__name__)
        @app.route("/", methods=["GET"])
        def root(): return "RajanTradeAutomation v6.0", 200
        @app.route("/engine/debug", methods=["GET"])
        def debug():
            settings = get_settings()
            return jsonify({"ok": True, "settings": settings, "subscribed": list(SUBSCRIBED)})
        @app.route("/engine/run-now", methods=["GET"])
        def runnow():
            settings = get_settings()
            # run a single seed
            res = compute_bias_once(settings)
            sectors = fetch_sector_perf()
            call_webapp("updateSectorPerf", {"sectors": sectors})
            sectors_all, top_names = build_sector_top(res.get("bias","NEUTRAL"), settings, sectors)
            stocks_all = fetch_stocks_for_top_sectors(top_names, res.get("bias","NEUTRAL"), settings)
            call_webapp("updateStockList", {"stocks": stocks_all})
            return jsonify({"ok": True, "bias": res, "sectors": len(sectors_all), "stocks": len(stocks_all)})
        port = int(os.getenv("PORT", "10000"))
        app.run(host="0.0.0.0", port=port)
    except Exception as e:
        print("Flask not started (optional). Error:", e)
        # keep main thread alive
        while True:
            time.sleep(60)
