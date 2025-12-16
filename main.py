# =====================================================
# Render Free Web Service
# Historical Candle Fetch (ONCE) + Flask Keep Alive
# =====================================================

from flask import Flask
import threading
import time
import os
import requests
from datetime import datetime
from fyers_apiv3 import fyersModel

# ---------------- ENV ----------------
FYERS_CLIENT_ID = os.environ["FYERS_CLIENT_ID"]
FYERS_ACCESS_TOKEN = os.environ["FYERS_ACCESS_TOKEN"]
WEBAPP_URL = os.environ["WEBAPP_URL"]

SYMBOL = "NSE:SBIN-EQ"
PORT = int(os.environ.get("PORT", 10000))

# ---------------- FYERS ----------------
fyers = fyersModel.FyersModel(
    client_id=FYERS_CLIENT_ID,
    token=FYERS_ACCESS_TOKEN,
    log_path=""
)

# ---------------- HISTORICAL LOGIC ----------------
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
    print("Fetching historical candles...")

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

    for c in candles[:3]:
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

    print("Historical candles DONE.")

# ---------------- FLASK ----------------
app = Flask(__name__)

@app.route("/")
def home():
    return "RajanTradeAutomation - Historical Candle Service Running"

# ---------------- STARTUP ----------------
if __name__ == "__main__":
    # Run historical fetch in background ONCE
    t = threading.Thread(target=fetch_first_3_candles, daemon=True)
    t.start()

    # Start web server (MANDATORY for free Render)
    app.run(host="0.0.0.0", port=PORT)
