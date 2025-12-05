from flask import Flask, request, jsonify
import requests
import os
import json

app = Flask(__name__)

# ---------------------------------------------------
# ENVIRONMENT VARIABLES
# ---------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "")
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY", "")
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI", "")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "")

# ---------------------------------------------------
# BASIC HEALTH CHECK
# ---------------------------------------------------
@app.get("/ping")
def ping():
    return "PONG"


# ---------------------------------------------------
# SETTINGS FROM GOOGLE SHEETS
# ---------------------------------------------------
@app.get("/getSettings")
def get_settings():
    try:
        url = WEBAPP_URL
        payload = {"action": "getSettings"}
        res = requests.post(url, json=payload)
        return res.text
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ---------------------------------------------------
# FYERS REDIRECT HANDLER (AUTH CODE RECEIVER)
# ---------------------------------------------------
@app.get("/fyers-redirect")
def fyers_redirect():
    code = request.args.get("auth_code", "")
    status = request.args.get("status", "")
    return f"""
    <h3>Status: {status}</h3>
    <p>Auth Code (copy safely):</p>
    <textarea rows='5' cols='120'>{code}</textarea>
    <p>हा auth code Render ENV मध्ये FYERS_ACCESS_TOKEN generate करताना वापरा.</p>
    """


# ---------------------------------------------------
# TEST ROUTE 1 — SYNC UNIVERSE
# ---------------------------------------------------
@app.get("/test/syncUniverse")
def test_sync_universe():
    test_payload = {
        "action": "syncUniverse",
        "payload": {
            "universe": [
                {"symbol": "NSE:SBIN-EQ", "name": "State Bank", "sector": "BANK", "is_fno": True, "enabled": True},
                {"symbol": "NSE:TCS-EQ", "name": "TCS", "sector": "IT", "is_fno": True, "enabled": True},
                {"symbol": "NSE:RELIANCE-EQ", "name": "Reliance", "sector": "OILGAS", "is_fno": True, "enabled": True}
            ]
        }
    }
    r = requests.post(WEBAPP_URL, json=test_payload)
    return r.text


# ---------------------------------------------------
# TEST ROUTE 2 — UPDATE SECTOR PERFORMANCE
# ---------------------------------------------------
@app.get("/test/sectorPerf")
def test_sector_perf():
    test_payload = {
        "action": "updateSectorPerf",
        "payload": {
            "sectors": [
                {"sector_name": "BANK", "sector_code": "BANK", "%chg": 1.05, "advances": 9, "declines": 3},
                {"sector_name": "IT", "sector_code": "IT", "%chg": -0.75, "advances": 5, "declines": 11},
                {"sector_name": "OILGAS", "sector_code": "OILGAS", "%chg": 0.20, "advances": 7, "declines": 2}
            ]
        }
    }
    r = requests.post(WEBAPP_URL, json=test_payload)
    return r.text


# ---------------------------------------------------
# TEST ROUTE 3 — STOCK LIST
# ---------------------------------------------------
@app.get("/test/stocks")
def test_stocks():
    test_payload = {
        "action": "updateStockList",
        "payload": {
            "stocks": [
                {"symbol": "NSE:SBIN-EQ", "direction_bias": "BUY", "%chg": 1.25, "sector": "BANK", "ltp": 622.4, "volume": 1250000, "selected": True},
                {"symbol": "NSE:TCS-EQ", "direction_bias": "SELL", "%chg": -1.15, "sector": "IT", "ltp": 3455.8, "volume": 820000, "selected": True},
                {"symbol": "NSE:RELIANCE-EQ", "direction_bias": "BUY", "%chg": 0.55, "sector": "OILGAS", "ltp": 2501.25, "volume": 1520000, "selected": False}
            ]
        }
    }
    r = requests.post(WEBAPP_URL, json=test_payload)
    return r.text


# ---------------------------------------------------
# TEST ROUTE 4 — CANDLE HISTORY (5-min candle)
# ---------------------------------------------------
@app.get("/test/candles")
def test_candles():
    test_payload = {
        "action": "pushCandle",
        "payload": {
            "candles": [
                {
                    "symbol": "NSE:SBIN-EQ",
                    "time": "2025-12-05T09:35:00+05:30",
                    "timeframe": "5m",
                    "open": 621,
                    "high": 623,
                    "low": 620.5,
                    "close": 622.4,
                    "volume": 155000,
                    "candle_index": 4,
                    "lowest_volume_so_far": 155000,
                    "is_signal": False,
                    "direction": "BUY"
                }
            ]
        }
    }
    r = requests.post(WEBAPP_URL, json=test_payload)
    return r.text


# ---------------------------------------------------
# TEST ROUTE 5 — SIGNAL
# ---------------------------------------------------
@app.get("/test/signal")
def test_signal():
    test_payload = {
        "action": "pushSignal",
        "payload": {
            "signals": [
                {
                    "symbol": "NSE:SBIN-EQ",
                    "direction": "BUY",
                    "signal_time": "2025-12-05T09:36:00+05:30",
                    "candle_index": 4,
                    "open": 621,
                    "high": 623,
                    "low": 620.5,
                    "close": 622.4,
                    "entry_price": 623,
                    "sl": 620.5,
                    "target_price": 628.0,
                    "risk_per_share": 2.5,
                    "rr": 2.0,
                    "status": "PENDING"
                }
            ]
        }
    }
    r = requests.post(WEBAPP_URL, json=test_payload)
    return r.text


# ---------------------------------------------------
# TEST ROUTE 6 — TRADE ENTRY
# ---------------------------------------------------
@app.get("/test/entry")
def test_entry():
    test_payload = {
        "action": "pushTradeEntry",
        "payload": {
            "symbol": "NSE:SBIN-EQ",
            "direction": "BUY",
            "entry_price": 623,
            "sl": 620.5,
            "target_price": 628.0,
            "qty_total": 100,
            "entry_time": "2025-12-05T09:37:10+05:30"
        }
    }
    r = requests.post(WEBAPP_URL, json=test_payload)
    return r.text


# ---------------------------------------------------
# TEST ROUTE 7 — EXIT (Partial or Final)
# ---------------------------------------------------
@app.get("/test/exit")
def test_exit():
    test_payload = {
        "action": "pushTradeExit",
        "payload": {
            "symbol": "NSE:SBIN-EQ",
            "exit_type": "PARTIAL",
            "exit_qty": 50,
            "exit_price": 625.5,
            "exit_time": "2025-12-05T10:10:00+05:30",
            "pnl": 1250,
            "status": "PARTIAL"
        }
    }
    r = requests.post(WEBAPP_URL, json=test_payload)
    return r.text


# ---------------------------------------------------
# FLASK RUNNER
# ---------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
