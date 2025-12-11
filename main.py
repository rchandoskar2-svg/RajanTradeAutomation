# ============================================================
# RajanTradeAutomation - main.py (FINAL v5.0)
# - Bias + Sector + Stock Engine
# - FYERS WebSocket integration (data -> 5m candle engine)
# ============================================================

import os, time, threading, requests, json, math
from datetime import datetime, timedelta

# optional imports - ensure in requirements.txt on Render
try:
    from nsetools import Nse
    NSE_CLIENT = Nse()
except Exception:
    NSE_CLIENT = None

# Fyers websocket client
# package name may vary; using pattern from executive sample
try:
    from fyers_apiv3.FyersWebsocket import data_ws
    FYERS_WS_AVAILABLE = True
except Exception:
    data_ws = None
    FYERS_WS_AVAILABLE = False

# ENV
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
FYERS_INSTRUMENTS_URL = os.getenv("FYERS_INSTRUMENTS_URL", "https://api.fyers.in/api/v2/instruments").strip()
FYERS_HISTORICAL_URL = os.getenv("FYERS_HISTORICAL_URL", "https://api.fyers.in/data-rest/v2/history").strip()
INTERVAL_SECS = int(os.getenv("INTERVAL_SECS", "60"))
MODE = os.getenv("MODE", "PAPER").upper()
AUTO_UNIVERSE = os.getenv("AUTO_UNIVERSE", "TRUE").upper() == "TRUE"

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

# ---------------- Bias / Sector / Stock engine (unchanged core)
SECTOR_INDEX_MAP = {
    "NIFTY BANK": "BANK", "NIFTY PSU BANK": "PSUBANK", "NIFTY OIL & GAS": "OILGAS",
    "NIFTY IT": "IT", "NIFTY PHARMA": "PHARMA", "NIFTY AUTO": "AUTO", "NIFTY FMCG": "FMCG",
    "NIFTY METAL": "METAL", "NIFTY FIN SERVICE": "FIN", "NIFTY REALTY": "REALTY", "NIFTY MEDIA": "MEDIA"
}

def get_nifty50_breadth():
    if NSE_CLIENT is None:
        return {"ok": False, "error": "NSE client not available"}
    try:
        q = NSE_CLIENT.get_index_quote("NIFTY 50")
        adv = int(q.get("advances",0)); dec = int(q.get("declines",0)); unc = int(q.get("unchanged",0))
        return {"ok": True, "advances": adv, "declines": dec, "unchanged": unc}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def compute_bias(adv, dec):
    if adv > dec: return "BUY"
    if dec > adv: return "SELL"
    return "NEUTRAL"

def compute_bias_strength(adv, dec, bias):
    total = adv + dec
    if total <= 0 or bias not in ("BUY","SELL"): return 0.0
    return (adv*100.0/total) if bias=="BUY" else (dec*100.0/total)

def fetch_all_sector_quotes():
    if NSE_CLIENT is None: return []
    try:
        all_idx = NSE_CLIENT.get_all_index_quote()
    except Exception:
        return []
    sectors=[]
    for item in all_idx:
        name = item.get("index") or item.get("indexSymbol")
        if not name or name not in SECTOR_INDEX_MAP: continue
        sectors.append({"sector_name": name, "sector_code": SECTOR_INDEX_MAP[name], "%chg": float(item.get("percentChange",0.0) or 0.0), "advances": int(item.get("advances",0) or 0), "declines": int(item.get("declines",0) or 0)})
    return sectors

def build_sector_universe_and_top(bias, settings):
    sectors = fetch_all_sector_quotes()
    if not sectors: return [], set()
    if bias=="SELL": sectors_sorted = sorted(sectors, key=lambda s: s["%chg"]); top_count = int(settings.get("SELL_SECTOR_COUNT",2) or 2)
    else: sectors_sorted = sorted(sectors, key=lambda s: s["%chg"], reverse=True); top_count = int(settings.get("BUY_SECTOR_COUNT",2) or 2)
    top_count = max(1, top_count)
    top = sectors_sorted[:top_count]; top_names = {s["sector_name"] for s in top}
    return sectors_sorted, top_names

def fetch_stocks_for_top_sectors(top_sector_names, bias, settings):
    if NSE_CLIENT is None or not top_sector_names: return []
    max_up = float(settings.get("MAX_UP_PERCENT",2.5)); max_down = float(settings.get("MAX_DOWN_PERCENT",-2.5))
    all_rows=[]
    for sec_name in top_sector_names:
        try:
            quotes = NSE_CLIENT.get_stock_quote_in_index(index=sec_name, include_index=False)
        except Exception:
            continue
        for q in quotes:
            sym = q.get("symbol"); 
            if not sym: continue
            pchg = float(q.get("pChange",0.0) or 0.0)
            ltp = float(q.get("ltp",0.0) or 0.0)
            vol = int(q.get("totalTradedVolume",0) or 0)
            selected = False
            if bias=="BUY":
                if pchg>0 and pchg<=max_up: selected=True
            elif bias=="SELL":
                if pchg<0 and pchg>=max_down: selected=True
            all_rows.append({"symbol": f"NSE:{sym}-EQ", "direction_bias": bias, "sector": sec_name, "%chg": pchg, "ltp": ltp, "volume": vol, "selected": selected})
    return all_rows

def run_engine_once(settings, push_to_sheets=True):
    if NSE_CLIENT is None: return {"ok": False, "error": "NSE client not available"}
    breadth = get_nifty50_breadth()
    if not breadth.get("ok"): return breadth
    adv = breadth["advances"]; dec = breadth["declines"]
    bias = compute_bias(adv, dec)
    strength = compute_bias_strength(adv, dec, bias)
    threshold = float(settings.get("BIAS_THRESHOLD_PERCENT",60) or 60)
    primary_enabled = str(settings.get("ENABLE_PRIMARY_STRATEGY","TRUE")).upper()=="TRUE"
    status_str = f"{bias}|{strength:.1f}|{threshold:.1f}"
    if strength >= threshold and bias in ("BUY","SELL") and primary_enabled:
        set_state("BIAS_STATUS", "OK|" + status_str)
    else:
        set_state("BIAS_STATUS", "WEAK_OR_OFF|" + status_str)
    sectors_all, top_sector_names = build_sector_universe_and_top(bias, settings)
    stocks_all = fetch_stocks_for_top_sectors(top_sector_names, bias, settings)
    if push_to_sheets:
        call_webapp("updateSectorPerf", {"sectors": sectors_all})
        call_webapp("updateStockList", {"stocks": stocks_all})
    return {"ok": True, "bias": bias, "advances": adv, "declines": dec, "strength": strength, "threshold": threshold, "sectors_count": len(sectors_all), "top_sectors": list(top_sector_names), "stocks_count": len(stocks_all)}

# ---------- Candle aggregator & 5m engine ----------
# this keeps a small in-memory buffer per symbol to build 5m candles from ticks (if using websocket ticks)
# When using direct 5m candles from provider, adapt accordingly.

CANDLE_BUFF = {}  # symbol -> list of tick dicts (timestamp, price, volume)
AGG_CANDLES = {}  # symbol -> list of 5m candles (recent)

def feed_tick(symbol, price, volume, ts=None):
    # ts = epoch seconds (float) or None -> now
    if ts is None: ts = time.time()
    buf = CANDLE_BUFF.setdefault(symbol, [])
    buf.append({"ts": ts, "price": price, "vol": volume})
    # optional: keep last N ticks only
    if len(buf) > 1000: del buf[0:-800]

def build_5m_candle_from_buf(symbol, timeframe_start_ts):
    # timeframe_start_ts in epoch seconds (start of 5m)
    ticks = [t for t in CANDLE_BUFF.get(symbol, []) if t["ts"] >= timeframe_start_ts and t["ts"] < timeframe_start_ts + 300]
    if not ticks: return None
    opens = ticks[0]["price"]; closes = ticks[-1]["price"]
    highs = max(t["price"] for t in ticks); lows = min(t["price"] for t in ticks)
    volume = sum(t["vol"] for t in ticks)
    return {"symbol": symbol, "time": datetime.fromtimestamp(timeframe_start_ts).isoformat(), "timeframe": "5m", "open": opens, "high": highs, "low": lows, "close": closes, "volume": volume}

def push_5m_candle_to_webapp(candle, candle_index):
    # compute lowestVolumeSoFar for that symbol's day (simple approach)
    sig = {"symbol": candle["symbol"], "time": candle["time"], "timeframe": candle["timeframe"], "open": candle["open"], "high": candle["high"], "low": candle["low"], "close": candle["close"], "volume": candle["volume"], "candle_index": candle_index}
    # compute lowest_volume_so_far
    prev = AGG_CANDLES.get(candle["symbol"], [])
    lowest = min([c["volume"] for c in prev] + [candle["volume"]]) if prev else candle["volume"]
    sig["lowest_volume_so_far"] = lowest
    # is_signal detection placeholder: will be updated by strategy (lowest-volume candle after initial fill)
    sig["is_signal"] = False
    # direction placeholder
    sig["direction"] = "BUY" if candle["close"] >= candle["open"] else "SELL"
    call_webapp("pushCandle", {"candles":[sig]})
    AGG_CANDLES.setdefault(candle["symbol"], []).append({"time": candle["time"], "volume": candle["volume"]})
    return sig

# ---------- FYERS WebSocket integration (uses executive sample pattern) ----------
FYERS_WS = None
SUBSCRIBED_SYMBOLS = set()
USE_FYERS_WS = FYERS_WS_AVAILABLE and bool(FYERS_ACCESS_TOKEN)

def fyers_onmessage(msg):
    # This callback will receive tick/quote updates. msg format depends on fyers lib.
    try:
        # Example structure handling — adapt if actual message structure differs.
        # If it's SymbolUpdate with 'd' key containing list of updates:
        if not isinstance(msg, dict):
            print("fy_msg not dict:", msg)
            return
        # The actual fyers message parsing will depend on library; try common fields:
        data = msg.get("d") or msg.get("data") or msg.get("response")
        if isinstance(data, list):
            for it in data:
                # Typical fields: 'symbol', 'ltp', 'volume' ... adjust as needed
                sym = it.get("symbol") or it.get("s")
                ltp = it.get("ltp") or it.get("last_price") or it.get("l")
                vol = it.get("volume") or it.get("v") or 0
                ts = time.time()
                if sym and ltp is not None:
                    feed_tick(sym, float(ltp), int(vol or 0), ts)
        else:
            # fallback single update
            sym = msg.get("symbol") or msg.get("s")
            ltp = msg.get("ltp")
            vol = msg.get("volume") or 0
            if sym and ltp is not None:
                feed_tick(sym, float(ltp), int(vol or 0), time.time())
    except Exception as e:
        print("fy_onmsg err:", e)

def fyers_onopen():
    print("FYERS WS opened")
    # subscribe to selected symbols from StockList via WebApp
    resp = call_webapp("getSettings", {})
    # get current StockList (call webapp directly)
    sl = call_webapp("getStockList", {}) if False else None  # optional - custom handler; fallback to fetch from sheet via getSettings not available
    # We'll subscribe to symbols from StockList sheet by reading that sheet via a small POST helper
    try:
        # We will request StockList by calling our GAS pushState trick: create an action to return StockList (not implemented)
        # Simpler: subscribe to a minimal default set for now (example), and allow dynamic subscribe via endpoint /subscribeSymbols
        pass
    except Exception as e:
        print("subscribe error:", e)

def fyers_onerror(err):
    print("FYERS WS error:", err)

def fyers_onclose(msg):
    print("FYERS WS closed:", msg)

def start_fyers_ws(sub_symbols=None):
    global FYERS_WS, SUBSCRIBED_SYMBOLS
    if not FYERS_WS_AVAILABLE:
        print("FYERS websocket lib not installed or available.")
        return
    if not FYERS_ACCESS_TOKEN:
        print("FYERS_ACCESS_TOKEN not set — cannot start WS.")
        return
    try:
        SUBSCRIBED_SYMBOLS = set(sub_symbols or [])
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

# ---------- Periodic aggregator thread to flush 5m candles ----------
def aggregator_cycle():
    """
    Every 5s check if any 5-minute boundary has passed for symbols with buffer and flush candle.
    Simpler approach: compute current 5m slot for now and build candle for previous slot.
    """
    last_checked_slot = None
    while True:
        try:
            now = datetime.utcnow() + timedelta(hours=5, minutes=30)  # IST
            # compute current slot start (rounded down to nearest 5 minutes)
            minute = (now.minute // 5) * 5
            slot_start = datetime(now.year, now.month, now.day, now.hour, minute, 0)
            slot_ts = slot_start.timestamp()
            if last_checked_slot is None:
                last_checked_slot = slot_ts
            # if new slot started, we build for previous slot
            if slot_ts != last_checked_slot:
                prev_slot = last_checked_slot
                # build for all symbols that have ticks
                for symbol in list(CANDLE_BUFF.keys()):
                    candle = build_5m_candle_from_buf(symbol, prev_slot)
                    if candle:
                        # candle_index: length of AGG_CANDLES+1 for that symbol
                        candle_index = len(AGG_CANDLES.get(symbol, [])) + 1
                        sig = push_5m_candle_to_webapp(candle, candle_index)
                        # After pushing candle, decide if it's the new lowest-volume and whether to generate a signal:
                        # Signal rule: after initial historical fill (we may require first 3 candles), identify lowest volume so far and mark it as signal
                        prev = AGG_CANDLES.get(symbol, [])
                        # if candle is lowest among prev+current and after at least 3 candles
                        vols = [c["volume"] for c in prev] + [candle["volume"]]
                        if len(vols) >= 3 and candle["volume"] == min(vols):
                            # create signal: direction rule (RED candle buy on break HIGH etc.)
                            # For simplicity create entry candidate with entry_price = candle.high (for BUY) or candle.low (for SELL)
                            direction = "BUY" if candle["close"] >= candle["open"] else "SELL"
                            entry_price = candle["high"] if direction=="BUY" else candle["low"]
                            sl = candle["low"] if direction=="BUY" else candle["high"]
                            # target at RR=2 -> simple: target = entry + 2*(entry-sl) for BUY
                            risk_per_share = abs(entry_price - sl)
                            if risk_per_share <= 0: continue
                            rr = float(2.0)
                            target = entry_price + rr * (entry_price - sl) if direction=="BUY" else entry_price - rr * (sl - entry_price)
                            # prepare signal payload
                            signal_payload = {
                                "signals": [
                                    {
                                        "symbol": candle["symbol"],
                                        "direction": direction,
                                        "signal_time": candle["time"],
                                        "candle_index": candle_index,
                                        "open": candle["open"],
                                        "high": candle["high"],
                                        "low": candle["low"],
                                        "close": candle["close"],
                                        "entry_price": entry_price,
                                        "sl": sl,
                                        "target_price": target,
                                        "risk_per_share": risk_per_share,
                                        "rr": rr,
                                        "status": "PENDING"
                                    }
                                ]
                            }
                            call_webapp("pushSignal", signal_payload)
                last_checked_slot = slot_ts
        except Exception as e:
            print("aggregator_cycle error:", e)
        time.sleep(5)

# ---------- Engine cycle background ----------
def engine_cycle():
    # initial universe sync
    try:
        if AUTO_UNIVERSE:
            # try syncing once at start
            # reuse earlier sync logic: call our test endpoint or rely on NSE client
            # we'll call run_engine_once at start
            pass
    except Exception as e:
        print("universe sync err:", e)
    while True:
        try:
            settings_resp = call_webapp("getSettings", {})
            settings = settings_resp.get("settings", {}) if isinstance(settings_resp, dict) else {}
            result = run_engine_once(settings, push_to_sheets=True)
            print("Engine run:", result)
        except Exception as e:
            print("ENGINE ERROR:", e)
        time.sleep(INTERVAL_SECS)

def start_background_threads():
    t1 = threading.Thread(target=engine_cycle, daemon=True)
    t2 = threading.Thread(target=aggregator_cycle, daemon=True)
    t1.start(); t2.start()
    # start fyers ws if available and token present
    if FYERS_WS_AVAILABLE and FYERS_ACCESS_TOKEN:
        # choose default symbols to subscribe from StockList - we rely on user to set in Settings or add subscribe API later
        default_symbols = []
        try:
            # attempt to pull current StockList via a GET-like WebApp helper (not implemented). For now we subscribe none.
            pass
        except:
            pass
        start_fyers_ws(default_symbols)

if __name__ == "__main__":
    start_background_threads()
    # Minimal Flask for debug/test routes (optional)
    from flask import Flask, jsonify
    app = Flask(__name__)
    @app.route("/", methods=["GET"])
    def root(): return "RajanTradeAutomation v5.0", 200
    @app.route("/engine/debug", methods=["GET"])
    def debug(): 
        settings = call_webapp("getSettings", {}).get("settings", {})
        return jsonify(run_engine_once(settings, push_to_sheets=False))
    @app.route("/engine/run-now", methods=["GET"])
    def runnow():
        settings = call_webapp("getSettings", {}).get("settings", {})
        return jsonify(run_engine_once(settings, push_to_sheets=True))
    @app.route("/test/pushCandle", methods=["POST"])
    def test_push_candle():
        payload = requests.get("https://httpbin.org/get").text
        return jsonify({"ok": True})
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
