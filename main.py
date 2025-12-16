# =====================================================
# RajanTradeAutomation – Historical Only (Stable)
# Render Free | No Flask | No Gunicorn
# =====================================================

import os
import time
import requests
from datetime import datetime, time as dtime
from fyers_apiv3 import fyersModel

# ---------------- ENV ----------------
FYERS_CLIENT_ID = os.environ["FYERS_CLIENT_ID"]
FYERS_ACCESS_TOKEN = os.environ["FYERS_ACCESS_TOKEN"]
WEBAPP_URL = os.environ["WEBAPP_URL"]

SYMBOL = "NSE:SBIN-EQ"

# ---------------- FYERS ----------------
fyers = fyersModel.FyersModel(
    client_id=FYERS_CLIENT_ID,
    token=FYERS_ACCESS_TOKEN,
    log_path=""
)

# ---------------- PUSH TO WEBAPP ----------------
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
        "source": "HIST"
    }
    r = requests.post(WEBAPP_URL, json=payload, timeout=10)
    print("PUSH:", payload, r.text)

# ---------------- HISTORICAL 9:15–9:30 ----------------
def fetch_915_930():
    print("Fetching 9:15–9:30 historical candles...")

    data = {
        "symbol": SYMBOL,
        "resolution": "5",
        "date_format": "1",
        "range_from": datetime.now().strftime("%Y-%m-%d"),
        "range_to": datetime.now().strftime("%Y-%m-%d"),
        "cont_flag": "1"
    }

    resp = fyers.history(data)
    candles = resp.get("candles", [])

    selected = []

    for c in candles:
        ts = datetime.fromtimestamp(c[0])
        t = ts.time()

        if dtime(9, 15) <= t < dtime(9, 30) and c[5] > 0:
            selected.append({
                "time": ts.strftime("%H:%M:%S"),
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": c[5]
            })

    selected.sort(key=lambda x: x["time"])

    if len(selected) != 3:
        print("⚠️ Expected 3 candles, got", len(selected))
        return

    for c in selected:
        print("HIST:", c)
        push_candle(c)
        time.sleep(1)

    print("✅ Historical 9:15–9:30 DONE")

# ---------------- MAIN ----------------
def main():
    print("ENGINE STARTED (historical-only mode)")

    # run historical ONCE
    fetch_915_930()

    print("Entering keep-alive loop...")

    # 🔒 KEEP RENDER ALIVE (THIS IS THE KEY)
    while True:
        try:
            requests.get(WEBAPP_URL + "?action=ping", timeout=10)
            print("Ping OK")
        except Exception as e:
            print("Ping failed:", e)

        time.sleep(60)

if __name__ == "__main__":
    main()
