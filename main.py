# ============================================================
# RajanTradeAutomation - Main Backend (Render / Flask)
# Version: 3.0 (Live Strategy + Test Suite)
# Role:
#   - Bridge between Fyers/NSE data & Google Sheets (WebApp.gs)
#   - Expose simple HTTP routes for health, settings & testing
# ============================================================

from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# ------------------------------------------------------------
# ENVIRONMENT VARIABLES  (set in Render → Environment)
# ------------------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY", "").strip()
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()


# ------------------------------------------------------------
# SMALL HELPERS
# ------------------------------------------------------------
def call_webapp(action, payload=None, timeout=15):
    """
    Generic helper to send JSON to Google Apps Script WebApp.gs

    request body:
    {
      "action": "<string>",
      "payload": {...}
    }
    """
    if payload is None:
        payload = {}

    if not WEBAPP_URL:
        return {"ok": False, "error": "WEBAPP_URL not configured in env"}

    body = {"action": action, "payload": payload}

    try:
        res = requests.post(WEBAPP_URL, json=body, timeout=timeout)
        txt = res.text
        # Try to parse JSON if possible, else return raw text
        try:
            j = res.json()
            return j
        except Exception:
            return {"ok": True, "raw": txt}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ------------------------------------------------------------
# ROOT + HEALTH CHECK
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def root():
    return "RajanTradeAutomation backend is LIVE ✅", 200


@app.route("/ping", methods=["GET"])
def ping():
    return "PONG", 200


# ------------------------------------------------------------
# SETTINGS FETCH (Render → WebApp → Sheets)
# ------------------------------------------------------------
@app.route("/getSettings", methods=["GET"])
def get_settings():
    """
    Calls WebApp.gs with action=getSettings
    and returns settings JSON directly to browser.
    """
    result = call_webapp("getSettings", {})
    return jsonify(result)


# ------------------------------------------------------------
# FYERS OAUTH REDIRECT HANDLER
# (Used only when generating fresh auth code)
# ------------------------------------------------------------
@app.route("/fyers-redirect", methods=["GET"])
def fyers_redirect():
    """
    Fyers will redirect to this URL with params:
      ?s=ok&auth_code=xxxxx&state=....
    We simply display the auth_code on screen so Rajan
    can copy it and use it to generate access_token.
    """
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


# ------------------------------------------------------------
# =============  TEST SUITE (no real trades)  ================
# सर्व खालील routes फक्त TEST साठी आहेत.
# हे browser मधून hit केल्यावर WebApp.gs ला dummy data
# जाईल व Sheets मध्ये rows दिसतील.
# ------------------------------------------------------------

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
# दोन्ही aliases देतो जेणेकरून गोंधळ नको:
#   /test/updateSectorPerf  आणि /test/sectorPerf
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
# aliases: /test/updateStockList  आणि /test/stocks
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
# aliases: /test/pushCandle आणि /test/candles
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
# FLASK ENTRY POINT (Render uses this to start app)
# ------------------------------------------------------------
if __name__ == "__main__":
    # Render usually sets PORT itself, but keep default 10000
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
