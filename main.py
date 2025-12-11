# ============================================================
# RajanTradeAutomation - Main Backend (Render / Flask)
# Version: 4.2 (Bias + Sector + Stock Engine + State + Skeleton Candles)
# ============================================================

from flask import Flask, request, jsonify
import requests
import os
import time
import threading
from datetime import datetime, timedelta

# ------------------------------------------------------------
# NSE CLIENT (for NIFTY50 bias + sector data)
# ------------------------------------------------------------
try:
    from nsetools import Nse   # pip install nsetools
    NSE_CLIENT = Nse()
except Exception:
    NSE_CLIENT = None

app = Flask(__name__)

# ------------------------------------------------------------
# ENVIRONMENT VARIABLES (Render → Environment)
# ------------------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

FYERS_INSTRUMENTS_URL = os.getenv("FYERS_INSTRUMENTS_URL", "").strip()
FYERS_HISTORICAL_URL = os.getenv("FYERS_HISTORICAL_URL", "").strip()

INTERVAL_SECS = int(os.getenv("INTERVAL_SECS", "60"))
MODE = os.getenv("MODE", "PAPER").upper()
AUTO_UNIVERSE = os.getenv("AUTO_UNIVERSE", "TRUE").upper() == "TRUE"


# ------------------------------------------------------------
# TIME HELPERS (IST)
# ------------------------------------------------------------
def now_ist():
    return datetime.utcnow() + timedelta(hours=5, minutes=30)


def parse_hhmm_to_today_ist(hhmm, default_hour=11, default_min=0):
    try:
        parts = str(hhmm).split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        h, m = default_hour, default_min
    now = now_ist()
    return now.replace(hour=h, minute=m, second=0, microsecond=0)


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


# ------------------------------------------------------------
# ROOT + HEALTH CHECK
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def root():
    return "RajanTradeAutomation backend is LIVE ⭐ v4.2", 200


@app.route("/ping", methods=["GET"])
def ping():
    return "PONG", 200


# ------------------------------------------------------------
# SETTINGS FETCH
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
    <p>हा code कुणालाही share करू नकोस. Render env मधील
    FYERS_ACCESS_TOKEN तयार करताना याचा वापर कर.</p>
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


def get_nifty50_breadth():
    """NIFTY 50 advances / declines घेते."""
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
    """Bias rule based on NIFTY50 breadth."""
    if advances > declines:
        return "BUY"
    elif declines > advances:
        return "SELL"
    else:
        return "NEUTRAL"


def compute_strength_percent(advances, declines):
    total = advances + declines
    if total <= 0:
        return 0.0
    return round(max(advances, declines) * 100.0 / float(total), 2)


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
        chg = float(item.get("percentChange", 0.0))
        adv = int(item.get("advances", 0) or 0)
        dec = int(item.get("declines", 0) or 0)

        sectors.append({
            "sector_name": name,
            "sector_code": code,
            "%chg": chg,
            "advances": adv,
            "declines": dec,
        })

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
    """Top sector मधील stocks + %chg filter."""
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

            pchg = float(q.get("pChange", 0.0) or 0.0)
            ltp = float(q.get("ltp", 0.0) or 0.0)
            vol = int(q.get("totalTradedVolume", 0) or 0)

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


def maybe_push_universe_to_sheets(settings):
    """AUTO_UNIVERSE असल्यास Universe sheet भरून दे (FnO indices मधील stocks)."""
    if not AUTO_UNIVERSE or NSE_CLIENT is None:
        return

    sectors = fetch_all_sector_quotes()
    universe_rows = []

    for sec in sectors:
        index_name = sec["sector_name"]
        try:
            quotes = NSE_CLIENT.get_stock_quote_in_index(index=index_name, include_index=False)
        except Exception:
            continue

        for q in quotes:
            sym = q.get("symbol")
            if not sym:
                continue
            universe_rows.append({
                "symbol": f"NSE:{sym}-EQ",
                "name": sym,
                "sector": index_name,
                "is_fno": True,       # simple assumption
                "enabled": True,
            })

    if universe_rows:
        call_webapp("syncUniverse", {"universe": universe_rows})


def run_engine_once(settings, push_to_sheets=True):
    """
    Full cycle:
      1) NIFTY50 breadth → bias + strength
      2) Sector perf → sort + top sectors
      3) Top sectors मधील stocks
      4) Sheets update + State sheet मध्ये bias info
    """
    if NSE_CLIENT is None:
        return {"ok": False, "error": "NSE client not available (install nsetools)"}

    # --- 1) breadth ---
    breadth = get_nifty50_breadth()
    if not breadth.get("ok"):
        return breadth

    adv = breadth["advances"]
    dec = breadth["declines"]
    bias = compute_bias(adv, dec)
    strength = compute_strength_percent(adv, dec)

    threshold = float(settings.get("BIAS_THRESHOLD_PERCENT", 60) or 60.0)
    max_trade_time_str = str(settings.get("MAX_TRADE_TIME", "11:00"))
    max_trades_per_day = int(settings.get("MAX_TRADES_PER_DAY", 5) or 5)

    max_trade_dt = parse_hhmm_to_today_ist(max_trade_time_str, 11, 0)
    time_ok = now_ist() <= max_trade_dt
    bias_ok = strength >= threshold and bias != "NEUTRAL"

    # --- 2) Universe auto fill (once per run; हलकं आहे) ---
    maybe_push_universe_to_sheets(settings)

    # --- 3) Sector + stocks ---
    sectors_all, top_sector_names = build_sector_universe_and_top(bias, settings)
    stocks_all = fetch_stocks_for_top_sectors(top_sector_names, bias, settings)

    if push_to_sheets:
        call_webapp("updateSectorPerf", {"sectors": sectors_all})
        call_webapp("updateStockList", {"stocks": stocks_all})

        # State sheet मध्ये bias + strength + constraints
        state_items = [
            {"key": "BREADTH_ADVANCES", "value": adv},
            {"key": "BREADTH_DECLINES", "value": dec},
            {"key": "BREADTH_UNCHANGED", "value": breadth.get("unchanged", 0)},
            {"key": "BREADTH_BIAS", "value": bias},
            {"key": "BREADTH_STRENGTH", "value": strength},
            {"key": "BIAS_THRESHOLD_PERCENT", "value": threshold},
            {"key": "MAX_TRADE_TIME", "value": max_trade_time_str},
            {"key": "MAX_TRADES_PER_DAY", "value": max_trades_per_day},
            {"key": "BIAS_OK_FOR_STRATEGY", "value": str(bias_ok)},
            {"key": "TIME_OK_FOR_ENTRY", "value": str(time_ok)},
        ]
        call_webapp("pushState", {"items": state_items})

    return {
        "ok": True,
        "advances": adv,
        "declines": dec,
        "unchanged": breadth.get("unchanged", 0),
        "bias": bias,
        "strength": strength,
        "threshold": threshold,
        "max_trade_time": max_trade_dt.isoformat(),
        "max_trades_per_day": max_trades_per_day,
        "sectors_count": len(sectors_all),
        "stocks_count": len(stocks_all),
        "top_sectors": list(top_sector_names),
    }


# ============================================================
#        SKELETON – LIVE CANDLE ENGINE (to be completed)
# ============================================================

def fetch_5min_candles_for_symbols(symbols):
    """
    TODO: इथे Fyers history / websocket वापरून
    live + historical 5-min candles आणायचे आहेत.
    सध्या stub → रिकामी list परत करतो, म्हणजे कुठलीही
    candle Sheets मध्ये जाणार नाही (safe).
    """
    _ = symbols  # unused
    return []


def run_candle_engine_once(settings):
    """
    पुढच्या स्टेजला:
      - StockList मधील Selected=TRUE stocks घ्यायचे
      - प्रत्येकासाठी first 3 candles + पुढील candles
      - Lowest Volume so far → signal candle
      - pushCandle + pushSignal + (नंतर) pushTradeEntry
    आत्तासाठी फक्त structure + log.
    """
    # TODO: पुढच्या टप्प्यात implement करु
    return {"ok": True, "implemented": False}


# ============================================================
#                    MAIN ENGINE LOOP
# ============================================================

def engine_cycle():
    while True:
        try:
            print("🔄 ENGINE CYCLE STARTED")
            settings_resp = call_webapp("getSettings", {})
            settings = settings_resp.get("settings", {}) if isinstance(settings_resp, dict) else {}

            result_bias = run_engine_once(settings, push_to_sheets=True)
            print("⚙ Bias/Sector/Stock result:", result_bias)

            # पुढच्या स्टेपला candle engine इथे call करू:
            # result_candles = run_candle_engine_once(settings)
            # print("🕒 Candle engine result:", result_candles)

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


# ============================================================
#                    TEST SUITE (unchanged)
# ============================================================

# ---------- 1) UNIVERSE TEST ----------
@app.route("/test/syncUniverse", methods=["GET"])
def test_sync_universe():
    payload = {
        "universe": [
            {
                "symbol": "NSE:SBIN-EQ",
                "name": "State Bank of India",
                "sector": "PSU BANK",
                "is_fno": True,
                "enabled": True
            },
            {
                "symbol": "NSE:TCS-EQ",
                "name": "TCS",
                "sector": "IT",
                "is_fno": True,
                "enabled": True
            },
            {
                "symbol": "NSE:RELIANCE-EQ",
                "name": "Reliance Industries",
                "sector": "OIL & GAS",
                "is_fno": True,
                "enabled": True
            }
        ]
    }
    result = call_webapp("syncUniverse", payload)
    return jsonify(result)


# (बाकी test routes – sector / stocks / candles / signals / trades – तशाच ठेवू शकतोस,
# हवे असल्यास इथेच ठेव किंवा आधीसारख्या main.py मधून copy करून टाक.)

# ------------------------------------------------------------
# FLASK ENTRY POINT
# ------------------------------------------------------------
if __name__ == "__main__":
  port = int(os.getenv("PORT", "10000"))
  app.run(host="0.0.0.0", port=port)
