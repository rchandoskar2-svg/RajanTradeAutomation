# ============================================================
# RajanTradeAutomation - Render Backend (AUTO LIVE ENGINE)
# Version: 5.0 – Full Automatic: Universe Sync + Prefill + Strategy
# ============================================================

from flask import Flask, request, jsonify
import requests
import os
import time
import threading
from datetime import datetime, time as dt_time, timedelta

try:
    from zoneinfo import ZoneInfo
except:
    from pytz import timezone as ZoneInfo

# NSE Tools (Bias + Sector)
try:
    from nsetools import Nse
    NSE_CLIENT = Nse()
except:
    NSE_CLIENT = None

app = Flask(__name__)

# ============================================================
# 🔐 ENVIRONMENT VARIABLES  (YOU DO NOT EDIT THE CODE)
# ============================================================

WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

# Your Fyers Keys (YOU MUST FILL THESE IN RENDER ENV)
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
FYERS_REFRESH_TOKEN = os.getenv("FYERS_REFRESH_TOKEN", "").strip()
FYERS_TOKEN_REFRESH_URL = os.getenv("FYERS_TOKEN_REFRESH_URL", "").strip()

FYERS_INSTRUMENTS_URL = os.getenv("FYERS_INSTRUMENTS_URL", "").strip()
FYERS_HISTORICAL_URL = os.getenv("FYERS_HISTORICAL_URL", "").strip()

INTERVAL_SECS = int(os.getenv("INTERVAL_SECS", "1800"))  # default Rajan: 1800
MODE = os.getenv("MODE", "PAPER").upper()

TZ_NAME = os.getenv("TZ_NAME", "Asia/Kolkata")
ZONE = ZoneInfo(TZ_NAME)

START_TIME = dt_time(9, 0)
PREFILL_START = dt_time(9, 15)
PREFILL_END = dt_time(9, 30)
STRATEGY_START = dt_time(9, 35)
END_TIME = dt_time(15, 30)

AUTO_UNIVERSE = os.getenv("AUTO_UNIVERSE", "TRUE") == "TRUE"
UNIVERSE_SOURCE = os.getenv("UNIVERSE_SOURCE", "FYERS")

# ============================================================
# 🛠 COMMON helpers
# ============================================================

def now_ts():
    return datetime.now(tz=ZONE)

def call_webapp(action, payload=None):
    if payload is None:
        payload = {}

    if not WEBAPP_URL:
        return {"ok": False, "error": "WEBAPP_URL not set"}

    try:
        r = requests.post(WEBAPP_URL, json={"action": action, "payload": payload}, timeout=30)
        try:
            return r.json()
        except:
            return {"ok": True, "raw": r.text}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def log(msg):
    print(f"[{now_ts().strftime('%H:%M:%S')}] {msg}")

# ============================================================
# 🔄 FYERS TOKEN REFRESH
# ============================================================

def refresh_fyers_token():
    global FYERS_ACCESS_TOKEN

    if not (FYERS_REFRESH_TOKEN and FYERS_TOKEN_REFRESH_URL):
        log("No refresh token configured — skipping refresh.")
        return False

    try:
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": FYERS_REFRESH_TOKEN,
            "client_id": FYERS_CLIENT_ID,
            "client_secret": FYERS_SECRET_KEY
        }

        r = requests.post(FYERS_TOKEN_REFRESH_URL, data=payload, timeout=15)

        if r.status_code != 200:
            log("Refresh failed: " + r.text)
            return False

        j = r.json()
        if "access_token" in j:
            FYERS_ACCESS_TOKEN = j["access_token"]
            log("✔ FYERS access token refreshed.")
            return True

        log("Unexpected refresh response: " + str(j))
        return False

    except Exception as e:
        log("Refresh error: " + str(e))
        return False

# ============================================================
# 🌐 UNIVERSE FETCH (AUTO)
# ============================================================

def fetch_universe():
    """
    Primary: FYERS Instrument API
    Backup: NSE sample list
    """

    rows = []

    # 1) FYERS instruments (if URL + token available)
    if FYERS_INSTRUMENTS_URL and FYERS_ACCESS_TOKEN:
        try:
            headers = {"Authorization": f"Bearer {FYERS_ACCESS_TOKEN}"}
            r = requests.get(FYERS_INSTRUMENTS_URL, headers=headers, timeout=25)

            if r.status_code == 200:
                data = r.json().get("data", [])
                for item in data:
                    try:
                        sym = item.get("symbol") or item.get("tradingsymbol")
                        name = item.get("name") or sym
                        sector = item.get("segment") or ""

                        rows.append({
                            "symbol": f"NSE:{sym}-EQ",
                            "name": name,
                            "sector": sector,
                            "is_fno": True,
                            "enabled": True
                        })
                    except:
                        continue

                log(f"✔ Universe loaded from FYERS: {len(rows)}")
                return rows
        except:
            log("Fyers universe fetch failed, fallback…")

    # 2) fallback
    sample = [
        {"symbol": "NSE:SBIN-EQ", "name": "SBI", "sector": "PSUBANK", "is_fno": True, "enabled": True},
        {"symbol": "NSE:TCS-EQ", "name": "TCS", "sector": "IT", "is_fno": True, "enabled": True},
        {"symbol": "NSE:RELIANCE-EQ", "name": "Reliance", "sector": "OILGAS", "is_fno": True, "enabled": True}
    ]
    log("⚠ Using fallback universe sample.")
    return sample


def sync_universe():
    uni = fetch_universe()
    return call_webapp("syncUniverse", {"universe": uni})

# ============================================================
# 🕒 9:15–9:30 PREFILL CANDLES
# ============================================================

def fetch_5m(symbol, start_ts, end_ts):
    """
    Fetch historical 5 minute candles.
    Expected format:
        [timestamp, open, high, low, close, volume]
    """

    if not (FYERS_HISTORICAL_URL and FYERS_ACCESS_TOKEN):
        return []

    try:
        headers = {"Authorization": f"Bearer {FYERS_ACCESS_TOKEN}"}
        params = {
            "symbol": symbol,
            "resolution": "5",
            "date_format": "0",
            "range_from": int(start_ts.timestamp()),
            "range_to": int(end_ts.timestamp())
        }

        r = requests.get(FYERS_HISTORICAL_URL, headers=headers, params=params, timeout=25)

        if r.status_code != 200:
            return []

        candles = []
        data = r.json().get("candles", [])
        idx = 1

        for c in data:
            candles.append({
                "symbol": symbol,
                "time": datetime.fromtimestamp(c[0], tz=ZONE).isoformat(),
                "timeframe": "5m",
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": c[5],
                "candle_index": idx,
                "lowest_volume_so_far": 0,
                "is_signal": False,
                "direction": ""
            })
            idx += 1

        return candles

    except:
        return []


def prefill_candles(universe):
    today = now_ts().date()

    start = datetime.combine(today, PREFILL_START, tzinfo=ZONE)
    end = datetime.combine(today, PREFILL_END, tzinfo=ZONE)

    batch = []
    for row in universe:
        sym = row["symbol"]
        data = fetch_5m(sym, start, end)
        batch.extend(data)

        if len(batch) >= 200:
            call_webapp("pushCandle", {"candles": batch})
            batch = []

    if batch:
        call_webapp("pushCandle", {"candles": batch})

    log("✔ Prefill complete.")

# ============================================================
# 🧠 DAILY ORCHESTRATION
# ============================================================

def orchestrate():
    """
    Fully automatic:
        09:00 → token refresh + universe sync
        09:15 → prefill
        09:35 → strategy engine ready
    """

    last_run = None

    while True:
        now = now_ts()

        if now.weekday() >= 5:  # Sat/Sun
            time.sleep(300)
            continue

        if last_run == now.date():
            time.sleep(120)
            continue

        if now.time() >= START_TIME:
            log("=== Morning automation started ===")

            refresh_fyers_token()
            uni = fetch_universe()
            sync_universe()

            # wait till 9:15
            while now_ts().time() < PREFILL_START:
                time.sleep(20)

            prefill_candles(uni)

            log("=== Automation done for today ===")
            last_run = now.date()

        time.sleep(30)

# ============================================================
# ENGINE CYCLE (sector perf + stocklist)
# ============================================================

@app.route("/engine/debug", methods=["GET"])
def engine_debug():
    return call_webapp("getSettings", {})

# ============================================================
# HTTP ROUTES
# ============================================================

@app.route("/", methods=["GET"])
def home():
    return "RajanTradeAutomation Backend 5.0 Running ✔", 200

def start_threads():
    threading.Thread(target=orchestrate, daemon=True).start()

start_threads()

# ============================================================
# START FLASK
# ============================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
