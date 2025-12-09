# ============================================================
# RajanTradeAutomation - Main Backend (Render / Flask)
# Version: 4.0 (Bias + Sector + Stock Engine + Candle engine foundation)
# ============================================================

from flask import Flask, request, jsonify
import requests
import os
import time
import threading
import traceback

# Optional nsetools (install in requirements for NSE quotes)
try:
    from nsetools import Nse
    NSE_CLIENT = Nse()
except Exception:
    NSE_CLIENT = None

app = Flask(__name__)

# ------------------------------------------------------------
# ENV VARIABLES (Render → Environment)
# Must set these in Render dashboard (secure)
# ------------------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL","").strip()   # Google Apps Script WebApp Exec URL (POST)
INTERVAL_SECS = int(os.getenv("INTERVAL_SECS","1800"))  # default 1800
MODE = os.getenv("MODE","PAPER").upper()  # PAPER or LIVE

# Fyers credentials (fill securely)
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID","").strip()
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY","").strip()
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI","").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN","").strip()
FYERS_REFRESH_TOKEN = os.getenv("FYERS_REFRESH_TOKEN","").strip()

# Chartink token if used
CHARTINK_TOKEN = os.getenv("CHARTINK_TOKEN","").strip()

# Bias threshold default fallback (in percent)
BIAS_THRESHOLD = float(os.getenv("BIAS_THRESHOLD","60"))

# ------------------------------------------------------------
# helper: call Google WebApp (Apps Script)
# ------------------------------------------------------------
def call_webapp(action, payload=None, timeout=20):
    if payload is None:
        payload = {}
    if not WEBAPP_URL:
        return {"ok": False, "error": "WEBAPP_URL not configured"}
    body = {"action": action, "payload": payload}
    try:
        r = requests.post(WEBAPP_URL, json=body, timeout=timeout)
        try:
            return r.json()
        except Exception:
            return {"ok": True, "raw": r.text}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ------------------------------------------------------------
# Health routes
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def root():
    return "RajanTradeAutomation backend LIVE v4.0", 200

@app.route("/ping", methods=["GET"])
def ping():
    return "PONG", 200

# ------------------------------------------------------------
# Utility: compute bias from advances/declines with threshold
# ------------------------------------------------------------
def compute_bias_with_threshold(adv, dec, threshold_pct=60.0):
    total = adv + dec
    if total == 0:
        return "NEUTRAL", 0.0
    if adv > dec:
        strength = (adv / total) * 100.0
        bias = "BUY" if strength >= threshold_pct else "NEUTRAL"
        return bias, strength
    elif dec > adv:
        strength = (dec / total) * 100.0
        bias = "SELL" if strength >= threshold_pct else "NEUTRAL"
        return bias, strength
    else:
        return "NEUTRAL", 50.0

# ------------------------------------------------------------
# NSE helpers
# ------------------------------------------------------------
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

# ------------------------------------------------------------
# fetch sectors (attempt using nsetools get_all_index_quote)
# ------------------------------------------------------------
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

def fetch_all_sector_quotes():
    if NSE_CLIENT is None:
        return []
    try:
        all_idx = NSE_CLIENT.get_all_index_quote()
    except Exception:
        return []
    sectors = []
    for item in all_idx:
        name = item.get("index") or item.get("indexSymbol") or item.get("name")
        if not name:
            continue
        if name not in SECTOR_INDEX_MAP:
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
    # This uses NSE index->members (nsetools doesn't easily provide index membership)
    # We'll attempt per-sector scraping via nsetools (limited). If not available, return empty.
    if NSE_CLIENT is None or not top_sector_names:
        return []
    max_up = float(settings.get("MAX_UP_PERCENT", 2.5))
    max_down = float(settings.get("MAX_DOWN_PERCENT", -2.5))
    all_rows = []
    # Best-effort: nsetools doesn't provide per-sector members directly; this is placeholder.
    # In practice, use a maintained universe list (Universe sheet or Chartink)
    return all_rows

def run_engine_once(settings, push_to_sheets=True):
    if NSE_CLIENT is None:
        return {"ok": False, "error": "NSE client not available (install nsetools)"}
    breadth_resp = get_nifty50_breadth()
    if not breadth_resp.get("ok"):
        return breadth_resp
    adv = breadth_resp["advances"]
    dec = breadth_resp["declines"]
    unc = breadth_resp.get("unchanged",0)
    bias, strength = compute_bias_with_threshold(adv, dec, float(settings.get("BIAS_THRESHOLD_PERCENT", BIAS_THRESHOLD)))
    sectors_all, top_sector_names = build_sector_universe_and_top(bias if bias!="NEUTRAL" else "BUY", settings)
    stocks_all = fetch_stocks_for_top_sectors(top_sector_names, bias, settings)
    if push_to_sheets:
        call_webapp("updateSectorPerf", {"sectors": sectors_all})
        call_webapp("updateStockList", {"stocks": stocks_all})
    return {"ok": True, "bias": bias, "strength": strength, "advances": adv, "declines": dec, "unchanged": unc, "sectors_count": len(sectors_all), "top_sectors": list(top_sector_names), "stocks_count": len(stocks_all)}

def engine_cycle():
    while True:
        try:
            print("ENGINE CYCLE START")
            settings_resp = call_webapp("getSettings",{})
            settings = settings_resp.get("settings",{}) if isinstance(settings_resp,dict) else {}
            result = run_engine_once(settings, push_to_sheets=True)
            print("Engine result:", result)
        except Exception as e:
            print("ENGINE ERROR:", str(e))
            traceback.print_exc()
        time.sleep(INTERVAL_SECS)

def start_engine():
    t = threading.Thread(target=engine_cycle, daemon=True)
    t.start()

start_engine()

# DEBUG route to run one cycle without pushing to sheets
@app.route("/engine/debug", methods=["GET"])
def engine_debug():
    settings_resp = call_webapp("getSettings",{})
    settings = settings_resp.get("settings",{}) if isinstance(settings_resp,dict) else {}
    result = run_engine_once(settings, push_to_sheets=False)
    return jsonify(result)

# ------------------------------------------------------------
# Simple test endpoints (as before) — keep for convenience
# ------------------------------------------------------------
@app.route("/test/pingwebapp", methods=["GET"])
def test_ping_webapp():
    return jsonify(call_webapp("ping",{}))

if __name__ == "__main__":
    port = int(os.getenv("PORT","10000"))
    app.run(host="0.0.0.0", port=port)
