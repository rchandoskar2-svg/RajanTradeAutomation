# =====================================================
# Historical Candle Fetch – TEST ONLY
# =====================================================

from fyers_apiv3 import fyersModel
import requests
import os
import time
from datetime import datetime

# ---------- ENV ----------
FYERS_CLIENT_ID = os.environ["FYERS_CLIENT_ID"]
FYERS_ACCESS_TOKEN = os.environ["FYERS_ACCESS_TOKEN"]
WEBAPP_URL = os.environ["WEBAPP_URL"]   # ends with /exec
SYMBOL = "NSE:SBIN-EQ"

# ---------- FYERS ----------
fyers = fyersModel.FyersModel(
    client_id=FYERS_CLIENT_ID,
    token=FYERS_ACCESS_TOKEN,
    log_path=""
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
        "source": "HIST"
    }
    r = requests.post(WEBAPP_URL, json=payload, timeout=10)
    print("PUSH:", payload, r.text)

def fetch_first_3_candles():
    # 9:15–9:30 = first 3 candles
    data = {
        "symbol": SYMBOL,
        "resolution": "5",
        "date_format": "1",
        "range_from": "2025-12-16",
        "range_to": "2025-12-16",
        "cont_flag": "1"
    }

    resp = fyers.history(data)
    candles = resp.get("candles", [])

    print("TOTAL CANDLES:", len(candles))

    first_three = candles[:3]

    for c in first_three:
        candle = {
            "time": datetime.fromtimestamp(c[0]).strftime("%H:%M:%S"),
            "open": c[1],
            "high": c[2],
            "low": c[3],
            "close": c[4],
            "volume": c[5]
        }
        print("HIST:", candle)
        push_candle(candle)
        time.sleep(1)

if __name__ == "__main__":
    fetch_first_3_candles()
