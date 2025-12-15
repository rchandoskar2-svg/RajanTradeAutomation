# ============================================================
# RajanTradeAutomation - Main Backend (Render / Flask)
# Version: 4.1 (patched) — Bias + Sector + Stock Engine + State
# ============================================================

from flask import Flask, request, jsonify
import requests
import os
import time
import threading

# ------------------------------------------------------------
# NSE CLIENT (for NIFTY50 bias + sector data)
# ------------------------------------------------------------
try:
    from nsetools import Nse
    NSE_CLIENT = Nse()
except Exception:
    NSE_CLIENT = None

app = Flask(__name__)

# ------------------------------------------------------------
# ENVIRONMENT VARIABLES (Render → Environment)
# ------------------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY", "").strip()
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

FYERS_INSTRUMENTS_URL = os.getenv("FYERS_INSTRUMENTS_URL", "https://api.fyers.in/api/v2/instruments").strip()
FYERS_HISTORICAL_URL = os.getenv("FYERS_HISTORICAL_URL", "https://api.fyers.in/data-rest/v2/history").strip()

INTERVAL_SECS = int(os.getenv("INTERVAL_SECS", "60"))  # default 60 sec
MODE = os.getenv("MODE", "PAPER").upper()
AUTO_UNIVERSE = os.getenv("AUTO_UNIVERSE", "TRUE").upper() == "TRUE"

# ------------------------------------------------------------
# COMMON HELPER → CALL WebApp.gs
# ------------------------------------------------------------
def call_webapp(action, payload=None, timeout=20):
    if payload is None:
        payload = {}
    if not WEBAPP_URL:
        return {"ok": False, "error": "WEBAPP_URL not configured"}
    body = {"action": action, "payload": payload}
    try:
        res = requests.post(WEBAPP_URL, json=body, timeout=timeout)
        try:
            return res.json()
        except Exception:
            return {"ok": True, "raw": res.text}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def set_state(key, value):
    """Write simple key/value to State sheet via WebApp pushState action."""
    try:
        payload = {"items": [{"key": key, "value": str(value)}]}
        # Use pushState (WebApp has pushState handler). Also accept setState if needed.
        return call_webapp("pushState", payload)
    except Exception as e:
        print("set_state error:", e)
        return {"ok": False, "error": str(e)}

# ------------------------------------------------------------
# ROOT + HEALTH CHECK
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def root():
    return "RajanTradeAutomation backend is LIVE ⭐ v4.1 (patched)", 200

@app.route("/ping", methods=["GET"])
def ping():
    return "PONG", 200

# ------------------------------------------------------------
# SETTINGS FETCH (Render → WebApp → Sheets)
# ------------------------------------------------------------
@app.route("/getSettings", methods=["GET"])
def get_settings():
    result = call_webapp("getSettings", {})
    return jsonify(result)

# ------------------------------------------------------------
# FYERS OAUTH REDIRECT (unchanged)
# ------------------------------------------------------------
@app.route("/fyers-redirect", methods=["GET"])
def fyers_redirect():
    status = request.args.get("s") or request.args.get("status", "")
    auth_code = request.args.get("auth_code", "")
    state = request.args.get("state", "")
    html = f"""
    <h2>Fyers Redirect Handler</h2>
    <p>Status: <b>{status}</b></p>
    <p>State: <b>{state}</b></p>
    <p><b>Auth Code (copy & save safely):</b></p>
    <textarea rows="5" cols="120">{auth_code}</textarea>
    <p>Do NOT share this code. Use it to obtain tokens for FYERS access token refresh flow.</p>
    """
    return html, 200

# ============================================================
#                  BIAS + SECTOR + STOCK ENGINE
# ============================================================

SECTOR_INDEX_MAP = {
    "NIFTY BANK": "BANK",
    "NIFTY PSU BANK": "PSUBANK",
    "NIFTY OIL & GAS": "OILGAS",
    "NIFTY IT": "IT",
    "NIFTY PHARMA": "PHARMA",
    "NIFTY AUTO": "AUTO",
    "NIFTY FMCG": "FMCG",
    "NIFTY METAL": "METAL",
    "NIFTY FIN SERVICE": "FIN",
    "NIFTY REALTY": "REALTY",
    "NIFTY MEDIA": "MEDIA",
}

def fetch_fyers_fno_universe():
    # Optional: use FYERS_INSTRUMENTS_URL to fetch FnO universe (stub)
    return []

def sync_universe_if_needed():
    if not AUTO_UNIVERSE:
        print("AUTO_UNIVERSE=FALSE → Universe manually managed.")
        return
    if NSE_CLIENT is None:
        print("NSE client missing, cannot sync universe.")
        return
    try:
        all_idx = NSE_CLIENT.get_all_index_quote()
    except Exception as e:
        print("sync_universe error:", e)
        return
    rows = []
    for item in all_idx:
        name = item.get("index") or item.get("indexSymbol")
        if not name or name not in SECTOR_INDEX_MAP:
            continue
        sec_name = name
        try:
            quotes = NSE_CLIENT.get_stock_quote_in_index(index=sec_name, include_index=False)
        except Exception:
            continue
        for q in quotes:
            sym = q.get("symbol")
            if not sym:
                continue
            symbol_full = f"NSE:{sym}-EQ"
            rows.append({
                "symbol": symbol_full,
                "name": sym,
                "sector": sec_name,
                "is_fno": True,
                "enabled": True,
            })
    payload = {"universe": rows}
    res = call_webapp("syncUniverse", payload)
    print("syncUniverse result:", res)

def get_nifty50_breadth():
    if NSE_CLIENT is None:
        return {"ok": False, "error": "NSE client not available (nsetools missing)"}
    try:
        q = NSE_CLIENT.get_index_quote("NIFTY 50")
        adv = int(q.get("advances", 0))
        dec = int(q.get("declines", 0))
        unc = int(q.get("unchanged", 0))
        return {"ok": True, "advances": adv, "declines": dec, "unchanged": unc}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def compute_bias(advances, declines):
    if advances > declines:
        return "BUY"
    elif declines > advances:
        return "SELL"
    else:
        return "NEUTRAL"

def fetch_all_sector_quotes():
    if NSE_CLIENT is None:
        return []
    try:
        all_idx = NSE_CLIENT.get_all_index_quote()
    except Exception:
        return []
    sectors = []
    for item in all_idx:
        name = item.get("index") or item.get("indexSymbol")
        if not name or name not in SECTOR_INDEX_MAP:
            continue
        code = SECTOR_INDEX_MAP[name]
        chg = float(item.get("percentChange", 0.0) or 0.0)
        adv = int(item.get("advances", 0) or 0)
        dec = int(item.get("declines", 0) or 0)
        sectors.append({"sector_name": name, "sector_code": code, "%chg": chg, "advances": adv, "declines": dec})
    return sectors

def build_sector_universe_and_top(bias, settings):
    sectors = fetch_all_sector_quotes()
    if not sectors:
        return [], set()
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
    if NSE_CLIENT is None or not top_sector_names:
        return []
    max_up = float(settings.get("MAX_UP_PERCENT", 2.5))
    max_down = float(settings.get("MAX_DOWN_PERCENT", -2.5))
    all_rows = []
    for sec_name in top_sector_names:
        try:
            quotes = NSE_CLIENT.get_stock_quote_in_index(index=sec_name, include_index=False)
        except Exception:
            continue
        for q in quotes:
            sym = q.get("symbol")
            if not sym:
                continue
            try:
                pchg = float(q.get("pChange", 0.0) or 0.0)
            except Exception:
                pchg = 0.0
            try:
                ltp = float(q.get("ltp", 0.0) or 0.0)
            except Exception:
                ltp = 0.0
            try:
                vol = int(q.get("totalTradedVolume", 0) or 0)
            except Exception:
                vol = 0
            selected = False
            if bias == "BUY":
                if pchg > 0 and pchg <= max_up:
                    selected = True
            elif bias == "SELL":
                if pchg < 0 and pchg >= max_down:
                    selected = True
            row = {
                "symbol": f"NSE:{sym}-EQ",
                "direction_bias": bias,
                "sector": sec_name,
                "%chg": pchg,
                "ltp": ltp,
                "volume": vol,
                "selected": selected,
            }
            all_rows.append(row)
    return all_rows

def compute_bias_strength(advances, declines, bias):
    total = advances + declines
    if total <= 0 or bias not in ("BUY", "SELL"):
        return 0.0
    if bias == "BUY":
        return advances * 100.0 / total
    else:
        return declines * 100.0 / total

def run_engine_once(settings, push_to_sheets=True):
    if NSE_CLIENT is None:
        return {"ok": False, "error": "NSE client not available (install nsetools)"}
    breadth = get_nifty50_breadth()
    if not breadth.get("ok"):
        return breadth
    adv = breadth["advances"]
    dec = breadth["declines"]
    bias = compute_bias(adv, dec)
    strength = compute_bias_strength(adv, dec, bias)
    threshold = float(settings.get("BIAS_THRESHOLD_PERCENT", 60) or 60)
    primary_enabled = str(settings.get("ENABLE_PRIMARY_STRATEGY", "TRUE")).upper() == "TRUE"
    status_str = f"{bias}|{strength:.1f}|{threshold:.1f}"
    if strength >= threshold and bias in ("BUY", "SELL") and primary_enabled:
        set_state("BIAS_STATUS", "OK|" + status_str)
    else:
        set_state("BIAS_STATUS", "WEAK_OR_OFF|" + status_str)
    sectors_all, top_sector_names = build_sector_universe_and_top(bias, settings)
    stocks_all = fetch_stocks_for_top_sectors(top_sector_names, bias, settings)
    if push_to_sheets:
        call_webapp("updateSectorPerf", {"sectors": sectors_all})
        call_webapp("updateStockList", {"stocks": stocks_all})
    max_trade_time = str(settings.get("MAX_TRADE_TIME", "11:00"))
    max_trades_per_day = int(settings.get("MAX_TRADES_PER_DAY", 5) or 5)
    return {
        "ok": True,
        "bias": bias,
        "advances": adv,
        "declines": dec,
        "unchanged": breadth.get("unchanged", 0),
        "strength": strength,
        "threshold": threshold,
        "sectors_count": len(sectors_all),
        "top_sectors": list(top_sector_names),
        "stocks_count": len(stocks_all),
        "max_trade_time": max_trade_time,
        "max_trades_per_day": max_trades_per_day,
    }

# ------------------- ENGINE LOOP -------------------

def engine_cycle():
    try:
        sync_universe_if_needed()
    except Exception as e:
        print("Universe sync error:", e)
    while True:
        try:
            print("🔄 ENGINE CYCLE STARTED, interval:", INTERVAL_SECS)
            settings_resp = call_webapp("getSettings", {})
            settings = settings_resp.get("settings", {}) if isinstance(settings_resp, dict) else {}
            result = run_engine_once(settings, push_to_sheets=True)
            print("⚙ Engine result:", result)
        except Exception as e:
            print("❌ ENGINE ERROR:", e)
        time.sleep(INTERVAL_SECS)

def start_engine():
    t = threading.Thread(target=engine_cycle, daemon=True)
    t.start()

start_engine()

# ------------------------------------------------------------
# DEBUG ROUTES
# ------------------------------------------------------------
@app.route("/engine/debug", methods=["GET"])
def engine_debug():
    settings_resp = call_webapp("getSettings", {})
    settings = settings_resp.get("settings", {}) if isinstance(settings_resp, dict) else {}
    result = run_engine_once(settings, push_to_sheets=False)
    return jsonify(result)

@app.route("/engine/run-now", methods=["GET"])
def engine_run_now():
    settings_resp = call_webapp("getSettings", {})
    settings = settings_resp.get("settings", {}) if isinstance(settings_resp, dict) else {}
    result = run_engine_once(settings, push_to_sheets=True)
    return jsonify(result)

# ------------------------------------------------------------
# TEST SUITE (unchanged)
# ------------------------------------------------------------
@app.route("/test/syncUniverse", methods=["GET"])
def test_sync_universe():
    payload = {
        "universe": [
            {"symbol": "NSE:SBIN-EQ", "name": "State Bank of India", "sector": "PSU BANK", "is_fno": True, "enabled": True},
            {"symbol": "NSE:TCS-EQ", "name": "TCS", "sector": "IT", "is_fno": True, "enabled": True},
            {"symbol": "NSE:RELIANCE-EQ", "name": "Reliance Industries", "sector": "OIL & GAS", "is_fno": True, "enabled": True}
        ]
    }
    result = call_webapp("syncUniverse", payload)
    return jsonify(result)

@app.route("/test/updateSectorPerf", methods=["GET"])
def test_update_sector_perf():
    payload = {"sectors": [
        {"sector_name": "PSU BANK", "sector_code": "PSUBANK", "%chg": 1.02, "advances": 9, "declines": 3},
        {"sector_name": "NIFTY OIL & GAS", "sector_code": "OILGAS", "%chg": 0.20, "advances": 7, "declines": 5}
    ]}
    result = call_webapp("updateSectorPerf", payload)
    return jsonify(result)

@app.route("/test/updateStockList", methods=["GET"])
def test_update_stock_list():
    payload = {"stocks": [
        {"symbol": "NSE:SBIN-EQ", "direction_bias": "BUY", "sector": "PSU BANK", "%chg": 1.25, "ltp": 622.40, "volume": 1250000, "selected": True}
    ]}
    result = call_webapp("updateStockList", payload)
    return jsonify(result)

@app.route("/test/pushCandle", methods=["GET"])
def test_push_candle():
    payload = {"candles": [
        {"symbol": "NSE:SBIN-EQ", "time": "2025-12-05T09:35:00+05:30", "timeframe": "5m", "open": 621.00, "high": 623.00, "low": 620.50, "close": 622.40, "volume": 155000, "candle_index": 4, "lowest_volume_so_far": 155000, "is_signal": False, "direction": "BUY"}
    ]}
    result = call_webapp("pushCandle", payload)
    return jsonify(result)

@app.route("/test/pushSignal", methods=["GET"])
def test_push_signal():
    payload = {"signals": [
        {"symbol": "NSE:SBIN-EQ", "direction": "BUY", "signal_time": "2025-12-05T09:36:00+05:30", "candle_index": 4, "open": 621.00, "high": 623.00, "low": 620.50, "close": 622.40, "entry_price": 623.00, "sl": 620.50, "target_price": 628.00, "risk_per_share": 2.50, "rr": 2.0, "status": "PENDING"}
    ]}
    result = call_webapp("pushSignal", payload)
    return jsonify(result)

@app.route("/test/pushTradeEntry", methods=["GET"])
def test_push_trade_entry():
    payload = {"symbol": "NSE:SBIN-EQ", "direction": "BUY", "entry_price": 623.00, "sl": 620.50, "target_price": 628.00, "qty_total": 100, "entry_time": "2025-12-05T09:37:10+05:30"}
    result = call_webapp("pushTradeEntry", payload)
    return jsonify(result)

@app.route("/test/pushTradeExit", methods=["GET"])
def test_push_trade_exit():
    payload = {"symbol": "NSE:SBIN-EQ", "exit_type": "PARTIAL", "exit_qty": 50, "exit_price": 625.50, "exit_time": "2025-12-05T10:10:00+05:30", "pnl": 1250.00, "status": "PARTIAL"}
    result = call_webapp("pushTradeExit", payload)
    return jsonify(result)

# ------------------------------------------------------------
# FLASK ENTRY POINT
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)


# ===============================
# FYERS WS TICK TEST (TEMP)
# ===============================

from fyers_apiv3.FyersWebsocket import data_ws
import os

@app.route("/ws-test", methods=["GET"])
def ws_test():
    access_token = os.getenv("FYERS_ACCESS_TOKEN")

    if not access_token:
        return "FYERS_ACCESS_TOKEN missing", 400

    def onmessage(message):
        print("WS TICK:", message)

    def onerror(message):
        print("WS ERROR:", message)

    def onclose(message):
        print("WS CLOSED:", message)

    def onopen():
        symbols = ["NSE:SBIN-EQ"]
        fyers.subscribe(symbols=symbols, data_type="SymbolUpdate")
        fyers.keep_running()

    fyers = data_ws.FyersDataSocket(
        access_token=access_token,
        log_path="",
        litemode=False,
        write_to_file=False,
        reconnect=True,
        on_connect=onopen,
        on_close=onclose,
        on_error=onerror,
        on_message=onmessage
    )

    fyers.connect()
    return "WS TEST STARTED – check Render logs", 200
