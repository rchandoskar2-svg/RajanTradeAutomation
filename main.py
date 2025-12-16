# =====================================================
# RajanTradeAutomation – Universal Start Engine
# Historical (Last 3 completed candles) + Live Ready
# =====================================================

import os
import time
import threading
import requests
from datetime import datetime, timedelta
from fyers_apiv3 import fyersModel
from flask import Flask

# ---------------- ENV ----------------
FYERS_CLIENT_ID = os.environ["FYERS_CLIENT_ID"]
FYERS_ACCESS_TOKEN = os.environ["FYERS_ACCESS_TOKEN"]
WEBAPP_URL = os.environ["WEBAPP_URL"]
PORT = int(os.environ.get("PORT", 10000))

SYMBOL = "NSE:SBIN-EQ"
TF_MINUTES = 5

# ---------------- FYERS ----------------
fyers = fyersModel.FyersModel(
    client_id=FYERS_CLIENT_ID,
    token=FYERS_ACCESS_TOKEN,
    log_path=""
)

# ---------------- FLASK (PORT ONLY) ----------------
app = Flask(__name__)

@app.route("/")
def home():
    return "RajanTradeAutomation Alive"

# ---------------- HELPERS ----------------
def floor_to_5min(dt):
    return dt - timedelta(
        minutes=dt.minute % TF_MINUTES,
        seconds=dt.second,
        microseconds=dt.microsecond
    )

def push_candle(c):
    payload = {
        "action": "pushCandle",
        "symbol": SYMBOL,
        "tf": "5m",
        "time": c["time"],
        "o": c["open"],
        "h": c["high"],
        "l": c["low"],
        "c": c["close"],
        "v": c["volume"],
        "source": c["source"]
    }
    r = requests.post(WEBAPP_URL, json=payload, timeout=10)
    print("PUSH:", payload["time"], r.text)

# ---------------- HISTORICAL (SMART) ----------------
def fetch_last_3_completed():
    print("📌 Fetching last 3 completed candles")

    now = datetime.now()
    current_slot = floor_to_5min(now)

    # Last completed candle END
    end_time = current_slot
    start_time = end_time - timedelta(minutes=15)

    data = {
        "symbol": SYMBOL,
        "resolution": "5",
        "date_format": "1",
        "range_from": start_time.strftime("%Y-%m-%d"),
        "range_to": end_time.strftime("%Y-%m-%d"),
        "cont_flag": "1"
    }

    resp = fyers.history(data)
    candles = resp.get("candles", [])

    target_times = [
        (end_time - timedelta(minutes=15)).strftime("%H:%M:%S"),
        (end_time - timedelta(minutes=10)).strftime("%H:%M:%S"),
        (end_time - timedelta(minutes=5)).strftime("%H:%M:%S"),
    ]

    selected = []
    for c in candles:
        ts = datetime.fromtimestamp(c[0])
        tstr = ts.strftime("%H:%M:%S")
        if tstr in target_times and c[5] > 0:
            selected.append({
                "time": tstr,
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": c[5],
                "source": "HIST"
            })

    selected.sort(key=lambda x: x["time"])

    for c in selected:
        print("HIST:", c["time"])
        push_candle(c)
        time.sleep(1)

    print("✅ Historical sync done")

# ---------------- BACKGROUND LOOP ----------------
def background_engine():
    fetch_last_3_completed()

    print("🚀 Ready for live candles")
    while True:
        try:
            requests.get(WEBAPP_URL + "?action=ping", timeout=10)
            print("Ping OK")
        except Exception as e:
            print("Ping failed:", e)
        time.sleep(60)

# ---------------- MAIN ----------------
if __name__ == "__main__":
    threading.Thread(target=background_engine, daemon=True).start()
    print(f"Flask running on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
