# ============================================================
# RajanTradeAutomation - Main Backend (Render / Flask)
# Version: 4.1 (Bias + Sector + Stock + Auto-Universe + Test)
# ============================================================

from flask import Flask, request, jsonify
import requests
import os
import time
import threading

# ------------------------------------------------------------
# NSE CLIENT (for NIFTY50 breadth + sector data)
# ------------------------------------------------------------
try:
    # requirements.txt मध्ये: nsetools
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

INTERVAL_SECS = int(os.getenv("INTERVAL_SECS", "1800"))  # 30 मिनिटे (तू 1800 ठेवले आहेस)
MODE = os.getenv("MODE", "PAPER").upper()

# Bias strength threshold (% मध्ये) – Settings sheet मधून पण override होईल
BIAS_THRESHOLD_DEFAULT = float(os.getenv("BIAS_THRESHOLD_PERCENT", "60"))

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
    return "RajanTradeAutomation backend is LIVE ⭐ v4.1", 200


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
    <p>हा code कुणालाही share करू नकोस. Render env मधील
    FYERS_ACCESS_TOKEN तयार करताना याचा वापर कर.</p>
    """
    return html, 200


# ============================================================
#                  BIAS + SECTOR + STOCK ENGINE
# ============================================================

# NSE index → SectorCode mapping (Sheets मधील SectorCode कॉलम साठी)
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
    """
    NIFTY 50 advances / declines घेते.
    nse.get_index_quote("NIFTY 50") मध्ये advances/declines field असतात.
    """
    if NSE_CLIENT is None:
        return {"ok": False, "error": "NSE client not available (nsetools missing)"}

    try:
        q = NSE_CLIENT.get_index_quote("NIFTY 50")
        adv = int(q.get("advances", 0) or 0)
        dec = int(q.get("declines", 0) or 0)
        unc = int(q.get("unchanged", 0) or 0)
        return {
            "ok": True,
            "advances": adv,
            "declines": dec,
            "unchanged": unc,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def compute_bias_with_threshold(advances, declines, threshold_percent):
    """
    Bias + strength:
      strength = max(adv, dec) / (adv+dec) * 100
      strength < threshold_percent → NEUTRAL (no trades)
      strength >= threshold_percent → BUY किंवा SELL
    """
    total = advances + declines
    if total <= 0:
        return "NEUTRAL", 0.0

    strength = (max(advances, declines) / float(total)) * 100.0

    if strength < threshold_percent:
        return "NEUTRAL", strength

    if advances > declines:
        return "BUY", strength
    elif declines > advances:
        return "SELL", strength
    else:
        return "NEUTRAL", strength


def fetch_all_sector_quotes():
    """
    NSE मधून सर्व indices quotes आणते,
    त्यातून आपल्याला लागणारे sector indices फिल्टर करते.
    """
    if NSE_CLIENT is None:
        return []

    try:
        all_idx = NSE_CLIENT.get_all_index_quote()
    except Exception:
        return []

    sectors = []
    for item in all_idx:
        name = item.get("index") or item.get("indexSymbol")
        if not name:
            continue

        if name not in SECTOR_INDEX_MAP:
            continue

        code = SECTOR_INDEX_MAP[name]
        chg = float(item.get("percentChange", 0.0) or 0.0)
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


def build_sector_universe_and_top(bias_for_sort, settings):
    """
    सर्व sector quotes घेऊन:
      - bias_for_sort = "BUY" → %chg desc
      - bias_for_sort = "SELL" → %chg asc
    sort करते आणि Settings मधल्या count प्रमाणे top sectors निवडते.
    परत देते:
      (sorted_sectors_list, top_sector_names_set)
    """
    sectors = fetch_all_sector_quotes()
    if not sectors:
        return [], set()

    if bias_for_sort == "SELL":
        sectors_sorted = sorted(sectors, key=lambda s: s["%chg"])
        top_count = int(settings.get("SELL_SECTOR_COUNT", 2) or 2)
    else:  # BUY
        sectors_sorted = sorted(sectors, key=lambda s: s["%chg"], reverse=True)
        top_count = int(settings.get("BUY_SECTOR_COUNT", 2) or 2)

    top_count = max(1, top_count)
    top = sectors_sorted[:top_count]
    top_names = {s["sector_name"] for s in top}

    return sectors_sorted, top_names


def fetch_stocks_for_top_sectors(top_sector_names, bias, settings):
    """
    निवडलेल्या sector names साठी NSE कडून त्या index चे stocks quotes घेते.
    Rajan rule (%chg filter):
      - BUY bias → 0 < %chg <= +MAX_UP_PERCENT
      - SELL bias → MAX_DOWN_PERCENT <= %chg < 0
    NOTE:
      - FnO-only filter अजून pending (TODO).
      - symbol format → NSE:SBIN-EQ
    """
    if NSE_CLIENT is None or not top_sector_names:
        return []

    max_up = float(settings.get("MAX_UP_PERCENT", 2.5))
    max_down = float(settings.get("MAX_DOWN_PERCENT", -2.5))

    all_rows = []

    for sec_name in top_sector_names:
        try:
            quotes = NSE_CLIENT.get_stock_quote_in_index(
                index=sec_name,
                include_index=False
            )
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
                "sector": sec_name,   # "NIFTY IT" etc.
                "%chg": pchg,
                "ltp": ltp,
                "volume": vol,
                "selected": selected,
            }
            all_rows.append(row)

    return all_rows


def run_engine_once(settings, push_to_sheets=True):
    """
    ONE full cycle:
      1) Settings मधून bias threshold वाचतो
      2) NIFTY 50 adv/dec → bias + strength
      3) सर्व sectors → sort + top sectors
      4) top sectors मधील stocks → %chg filter
      5) Universe तयार करतो (आजच्या candidate stocks चा)
      6) SectorPerf + StockList + Universe Sheets ला push (optional)
    """
    if NSE_CLIENT is None:
        return {"ok": False, "error": "NSE client not available (install nsetools)"}

    # --- Settings मधून threshold घे ---
    try:
        threshold = float(settings.get("BIAS_THRESHOLD_PERCENT", BIAS_THRESHOLD_DEFAULT))
    except Exception:
        threshold = BIAS_THRESHOLD_DEFAULT

    # --- 1) NIFTY 50 breadth ---
    breadth = get_nifty50_breadth()
    if not breadth.get("ok"):
        return breadth

    adv = breadth["advances"]
    dec = breadth["declines"]

    bias, strength = compute_bias_with_threshold(adv, dec, threshold)

    # --- 2) Sector universe + top sectors ---
    # strength कमी असला तरी sectors दिसलेले बरे, म्हणून sort bias वेगळा:
    sort_bias = "BUY" if adv >= dec else "SELL"
    sectors_all, top_sector_names = build_sector_universe_and_top(sort_bias, settings)

    # --- 3) Stocks for top sectors (strength पुरेशी असेल तेव्हाच) ---
    if bias in ("BUY", "SELL"):
        stocks_all = fetch_stocks_for_top_sectors(top_sector_names, bias, settings)
    else:
        stocks_all = []

    # --- 4) Universe तयार कर (आजच्या stocks वरून) ---
    universe_rows = []
    for s in stocks_all:
        universe_rows.append({
            "symbol": s["symbol"],
            "name": "",                # भविष्यात actual name fill करू
            "sector": s["sector"],
            "is_fno": True,            # सध्या assume FnO, TODO: real FnO filter
            "enabled": True
        })

    # --- 5) Push to Sheets (optional) ---
    if push_to_sheets:
        if universe_rows:
            call_webapp("syncUniverse", {"universe": universe_rows})
        else:
            # रिकामे universe पण clear करतो
            call_webapp("syncUniverse", {"universe": []})

        call_webapp("updateSectorPerf", {"sectors": sectors_all})
        call_webapp("updateStockList", {"stocks": stocks_all})

    return {
        "ok": True,
        "bias": bias,
        "strength": round(strength, 2),
        "threshold": threshold,
        "advances": adv,
        "declines": dec,
        "unchanged": breadth.get("unchanged", 0),
        "sectors_count": len(sectors_all),
        "top_sectors": list(top_sector_names),
        "stocks_count": len(stocks_all),
    }


# ------------------------------------------------------------
# BACKGROUND ENGINE LOOP
# ------------------------------------------------------------
def engine_cycle():
    """
    Background engine: INTERVAL_SECS नंतर नंतर चालू राहील.
    फक्त bias + sector + stock + universe stage इथे handle होतो.
    Candle / WebSocket stage पुढच्या version मध्ये जोडू.
    """
    while True:
        try:
            print("🔄 ENGINE CYCLE STARTED")

            settings_resp = call_webapp("getSettings", {})
            settings = settings_resp.get("settings", {}) if isinstance(settings_resp, dict) else {}

            result = run_engine_once(settings, push_to_sheets=True)
            print("⚙ Engine result:", result)

        except Exception as e:
            print("❌ ENGINE ERROR:", e)

        time.sleep(INTERVAL_SECS)


def start_engine():
    # Render वर app import होताच background thread सुरू होईल.
    t = threading.Thread(target=engine_cycle, daemon=True)
    t.start()


start_engine()


# ------------------------------------------------------------
# DEBUG / MANUAL RUN ROUTES
# ------------------------------------------------------------
@app.route("/engine/debug", methods=["GET"])
def engine_debug():
    """
    फक्त calculation दाखवतो, Sheets disturb न करता.
    """
    settings_resp = call_webapp("getSettings", {})
    settings = settings_resp.get("settings", {}) if isinstance(settings_resp, dict) else {}
    result = run_engine_once(settings, push_to_sheets=False)
    return jsonify(result)


@app.route("/engine/run-now", methods=["GET"])
def engine_run_now():
    """
    एकदा full cycle चालवतो आणि Sheets मध्ये
    Universe + SectorPerf + StockList push करतो.
    """
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


# ---------- 2) SECTOR PERFORMANCE TEST ----------
@app.route("/test/updateSectorPerf", methods=["GET"])
@app.route("/test/sectorPerf", methods=["GET"])
def test_update_sector_perf():
    payload = {
        "sectors": [
            {
                "sector_name": "PSU BANK",
                "sector_code": "PSUBANK",
                "%chg": 1.02,
                "advances": 9,
                "declines": 3
            },
            {
                "sector_name": "NIFTY OIL & GAS",
                "sector_code": "OILGAS",
                "%chg": 0.20,
                "advances": 7,
                "declines": 5
            },
            {
                "sector_name": "AUTOMOBILE",
                "sector_code": "AUTO",
                "%chg": -0.12,
                "advances": 5,
                "declines": 7
            },
            {
                "sector_name": "FINANCIAL SERVICES",
                "sector_code": "FIN",
                "%chg": -0.77,
                "advances": 3,
                "declines": 11
            }
        ]
    }

    result = call_webapp("updateSectorPerf", payload)
    return jsonify(result)


# ---------- 3) STOCK LIST TEST ----------
@app.route("/test/updateStockList", methods=["GET"])
@app.route("/test/stocks", methods=["GET"])
def test_update_stock_list():
    payload = {
        "stocks": [
            {
                "symbol": "NSE:SBIN-EQ",
                "direction_bias": "BUY",
                "sector": "PSU BANK",
                "%chg": 1.25,
                "ltp": 622.40,
                "volume": 1250000,
                "selected": True
            },
            {
                "symbol": "NSE:TCS-EQ",
                "direction_bias": "SELL",
                "sector": "IT",
                "%chg": -1.15,
                "ltp": 3455.80,
                "volume": 820000,
                "selected": True
            },
            {
                "symbol": "NSE:RELIANCE-EQ",
                "direction_bias": "BUY",
                "sector": "OIL & GAS",
                "%chg": 0.55,
                "ltp": 2501.25,
                "volume": 1520000,
                "selected": False
            }
        ]
    }

    result = call_webapp("updateStockList", payload)
    return jsonify(result)


# ---------- 4) CANDLE HISTORY TEST ----------
@app.route("/test/pushCandle", methods=["GET"])
@app.route("/test/candles", methods=["GET"])
def test_push_candle():
    payload = {
        "candles": [
            {
                "symbol": "NSE:SBIN-EQ",
                "time": "2025-12-05T09:35:00+05:30",  # 4th 5m candle close
                "timeframe": "5m",
                "open": 621.00,
                "high": 623.00,
                "low": 620.50,
                "close": 622.40,
                "volume": 155000,
                "candle_index": 4,
                "lowest_volume_so_far": 155000,
                "is_signal": False,
                "direction": "BUY"
            }
        ]
    }

    result = call_webapp("pushCandle", payload)
    return jsonify(result)


# ---------- 5) SIGNAL TEST ----------
@app.route("/test/pushSignal", methods=["GET"])
@app.route("/test/signal", methods=["GET"])
def test_push_signal():
    payload = {
        "signals": [
            {
                "symbol": "NSE:SBIN-EQ",
                "direction": "BUY",
                "signal_time": "2025-12-05T09:36:00+05:30",
                "candle_index": 4,
                "open": 621.00,
                "high": 623.00,
                "low": 620.50,
                "close": 622.40,
                "entry_price": 623.00,
                "sl": 620.50,
                "target_price": 628.00,
                "risk_per_share": 2.50,
                "rr": 2.0,
                "status": "PENDING"
            }
        ]
    }

    result = call_webapp("pushSignal", payload)
    return jsonify(result)


# ---------- 6) TRADE ENTRY TEST ----------
@app.route("/test/pushTradeEntry", methods=["GET"])
@app.route("/test/entry", methods=["GET"])
def test_push_trade_entry():
    payload = {
        "symbol": "NSE:SBIN-EQ",
        "direction": "BUY",
        "entry_price": 623.00,
        "sl": 620.50,
        "target_price": 628.00,
        "qty_total": 100,
        "entry_time": "2025-12-05T09:37:10+05:30"
    }

    result = call_webapp("pushTradeEntry", payload)
    return jsonify(result)


# ---------- 7) TRADE EXIT TEST ----------
@app.route("/test/pushTradeExit", methods=["GET"])
@app.route("/test/exit", methods=["GET"])
def test_push_trade_exit():
    payload = {
        "symbol": "NSE:SBIN-EQ",
        "exit_type": "PARTIAL",       # SL / PARTIAL / FINAL / FORCE
        "exit_qty": 50,
        "exit_price": 625.50,
        "exit_time": "2025-12-05T10:10:00+05:30",
        "pnl": 1250.00,
        "status": "PARTIAL"
    }

    result = call_webapp("pushTradeExit", payload)
    return jsonify(result)


# ------------------------------------------------------------
# FLASK ENTRY POINT
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
