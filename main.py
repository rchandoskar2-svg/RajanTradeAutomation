# ============================================================
# RajanTradeAutomation - Main Backend (Render / Flask)
# Version: 4.0 (Live Strategy Engine Ready + Test Suite)
# ============================================================

from flask import Flask, request, jsonify
import requests
import os
import time
import threading

app = Flask(__name__)

# ------------------------------------------------------------
# ENVIRONMENT VARIABLES (Render → Environment)
# ------------------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY", "").strip()
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

INTERVAL_SECS = int(os.getenv("INTERVAL_SECS", "60"))   # Used for engine cycle
MODE = os.getenv("MODE", "PAPER").upper()


# ------------------------------------------------------------
# SIMPLE HELPERS
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
        except:
            return {"ok": True, "raw": res.text}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ------------------------------------------------------------
# ROOT + HEALTH CHECK
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def root():
    return "RajanTradeAutomation backend is LIVE ⭐ v4.0", 200


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
# FYERS OAUTH REDIRECT
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
    <p><b>Auth Code:</b></p>
    <textarea rows="5" cols="120">{auth_code}</textarea>
    """
    return html, 200


# ============================================================
#          CORE STRATEGY LOGIC (Bias, Sector, Stock)
# ============================================================
def choose_bias_and_candidates(
    nifty_advances,
    nifty_declines,
    sectors,
    stocks,
    settings,
):
    """Pure logic engine — returns:
       bias, chosen sectors, chosen candidate stocks
    """

    # -----------------------------
    # 1) Decide bias from NIFTY 50
    # -----------------------------
    if nifty_advances > nifty_declines:
        bias = "BUY"
    elif nifty_declines > nifty_advances:
        bias = "SELL"
    else:
        bias = "BUY"   # tie case → BUY

    buy_sector_count = int(settings.get("BUY_SECTOR_COUNT", 2))
    sell_sector_count = int(settings.get("SELL_SECTOR_COUNT", 2))

    max_up = float(settings.get("MAX_UP_PERCENT", 2.5))
    max_down = float(settings.get("MAX_DOWN_PERCENT", -2.5))

    # -----------------------------
    # 2) Sector selection
    # -----------------------------
    if bias == "BUY":
        sectors_sorted = sorted(sectors, key=lambda s: float(s.get("%chg", 0.0)), reverse=True)
        top_sectors = sectors_sorted[:buy_sector_count]
    else:
        sectors_sorted = sorted(sectors, key=lambda s: float(s.get("%chg", 0.0)))
        top_sectors = sectors_sorted[:sell_sector_count]

    top_sector_codes = {s["sector_code"] for s in top_sectors}

    # -----------------------------
    # 3) Stock selection
    # -----------------------------
    candidates = []
    for s in stocks:
        if not s.get("is_fno", False):
            continue

        if s.get("sector_code") not in top_sector_codes:
            continue

        chg = float(s.get("%chg", 0.0))

        if bias == "BUY":
            if 0 < chg <= max_up:
                candidates.append(s)
        else:
            if max_down <= chg < 0:
                candidates.append(s)

    return {
        "bias": bias,
        "top_sectors": top_sectors,
        "candidates": candidates
    }


# ============================================================
#                 LIVE ENGINE SKELETON (Run Cycle)
# ============================================================

def get_nifty_breadth():
    """TODO: Replace with actual NSE/Fyers breadth API."""
    return 32, 18     # dummy return for now


def get_live_sector_data():
    """TODO: Replace with Fyers sector API."""
    return []


def get_live_stock_data():
    """TODO: Replace with Fyers quotes for FnO list."""
    return []


def engine_cycle():
    """Runs once every INTERVAL_SECS seconds."""
    while True:
        try:
            print("🔄 ENGINE CYCLE STARTED")

            # ------------------------------------
            # 1) Load settings
            # ------------------------------------
            settings_resp = call_webapp("getSettings", {})
            settings = settings_resp.get("settings", {})
            print("⚙ Settings:", settings)

            # ------------------------------------
            # 2) Get market breadth
            # ------------------------------------
            adv, dec = get_nifty_breadth()

            # ------------------------------------
            # 3) Get sectors & stocks snapshots
            # ------------------------------------
            sector_snap = get_live_sector_data()
            stock_snap = get_live_stock_data()

            # ------------------------------------
            # 4) Apply Rajan's Logic
            # ------------------------------------
            selection = choose_bias_and_candidates(
                adv,
                dec,
                sector_snap,
                stock_snap,
                settings
            )

            bias = selection["bias"]
            top_sectors = selection["top_sectors"]
            candidates = selection["candidates"]

            print("➡ Bias:", bias)
            print("➡ Sectors:", top_sectors)
            print("➡ Candidates:", len(candidates))

            # ------------------------------------
            # 5) Push SectorPerf → Sheets
            # ------------------------------------
            payload = {"sectors": sector_snap}
            call_webapp("updateSectorPerf", payload)

            # ------------------------------------
            # 6) Push StockList → Sheets
            # ------------------------------------
            stock_rows = []
            for s in stock_snap:
                stock_rows.append({
                    "symbol": s["symbol"],
                    "direction_bias": bias,
                    "sector": s["sector_code"],
                    "%chg": s["%chg"],
                    "ltp": s["ltp"],
                    "volume": s["volume"],
                    "selected": s in candidates
                })

            call_webapp("updateStockList", {"stocks": stock_rows})

            print("✔ ENGINE CYCLE DONE")

        except Exception as e:
            print("❌ ENGINE ERROR:", e)

        time.sleep(INTERVAL_SECS)


# ------------------------------------------------------------
# ENGINE START (Background Thread)
# ------------------------------------------------------------
def start_engine():
    t = threading.Thread(target=engine_cycle, daemon=True)
    t.start()

start_engine()


# ============================================================
#                TEST SUITE (unchanged)
# ============================================================

@app.route("/test/syncUniverse", methods=["GET"])
def test_sync_universe():
    payload = {
        "universe": [
            {"symbol": "NSE:SBIN-EQ", "name": "State Bank of India", "sector": "PSUBANK", "is_fno": True, "enabled": True},
            {"symbol": "NSE:TCS-EQ", "name": "TCS", "sector": "IT", "is_fno": True, "enabled": True},
            {"symbol": "NSE:RELIANCE-EQ", "name": "Reliance", "sector": "OILGAS", "is_fno": True, "enabled": True}
        ]
    }
    return jsonify(call_webapp("syncUniverse", payload))


@app.route("/test/updateSectorPerf", methods=["GET"])
def test_update_sector_perf():
    payload = {
        "sectors": [
            {"sector_name": "PSU BANK", "sector_code": "PSUBANK", "%chg": -2.5, "advances": 3, "declines": 9},
            {"sector_name": "IT", "sector_code": "IT", "%chg": 1.5, "advances": 7, "declines": 5},
            {"sector_name": "OIL & GAS", "sector_code": "OILGAS", "%chg": -4.2, "advances": 2, "declines": 10}
        ]
    }
    return jsonify(call_webapp("updateSectorPerf", payload))


@app.route("/test/updateStockList", methods=["GET"])
def test_update_stock_list():
    payload = {
        "stocks": [
            {"symbol": "NSE:SBIN-EQ", "direction_bias": "BUY", "sector": "PSUBANK", "%chg": 1.25, "ltp": 622.40, "volume": 1250000, "selected": True},
            {"symbol": "NSE:TCS-EQ", "direction_bias": "SELL", "sector": "IT", "%chg": -1.15, "ltp": 3455.80, "volume": 820000, "selected": True}
        ]
    }
    return jsonify(call_webapp("updateStockList", payload))


@app.route("/test/pushCandle", methods=["GET"])
def test_push_candle():
    payload = {
        "candles": [{
            "symbol": "NSE:SBIN-EQ",
            "time": "2025-12-05T09:35:00+05:30",
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
        }]
    }
    return jsonify(call_webapp("pushCandle", payload))


@app.route("/test/pushSignal", methods=["GET"])
def test_push_signal():
    payload = {
        "signals": [{
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
        }]
    }
    return jsonify(call_webapp("pushSignal", payload))


@app.route("/test/pushTradeEntry", methods=["GET"])
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
    return jsonify(call_webapp("pushTradeEntry", payload))


@app.route("/test/pushTradeExit", methods=["GET"])
def test_push_trade_exit():
    payload = {
        "symbol": "NSE:SBIN-EQ",
        "exit_type": "PARTIAL",
        "exit_qty": 50,
        "exit_price": 625.50,
        "exit_time": "2025-12-05T10:10:00+05:30",
        "pnl": 1250.00,
        "status": "PARTIAL"
    }
    return jsonify(call_webapp("pushTradeExit", payload))


# ------------------------------------------------------------
# FLASK ENTRY POINT
# ------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
