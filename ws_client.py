"""
ws_client.py - Fyers Data WebSocket test (v1)
- ENV मधून FYERS_CLIENT_ID + FYERS_ACCESS_TOKEN वाचतो
- काही symbols साठी live ticks print करतो
"""

import os
import json
import time
from fyers_apiv3 import fyersModel


FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

# live test साठी काही basic symbols (नंतर FnO universe लावू)
SYMBOLS = [
    "NSE:NIFTY50-INDEX",
    "NSE:BANKNIFTY-INDEX",
    "NSE:RELIANCE-EQ",
]


def on_message(message):
    """प्रत्येक tick आली की इथे callback येतो."""
    try:
        data = json.loads(message)
    except Exception:
        print("RAW:", message)
        return

    print("WS TICK:", json.dumps(data)[:300])


def on_error(message):
    print("WS ERROR:", message)


def on_close(message):
    print("WS CLOSED:", message)


def on_open(ws):
    """
    कनेक्शन open झाल्यावर लगेच subscribe करतो.
    """
    print("WS OPENED, subscribing symbols:", SYMBOLS)
    # v3 data websocket साठी fyersModel मध्ये data_ws client आहे
    ws.subscribe(symbols=SYMBOLS, data_type="symbolData")


def start_ws():
    if not FYERS_CLIENT_ID or not FYERS_ACCESS_TOKEN:
        print("Missing FYERS_CLIENT_ID or FYERS_ACCESS_TOKEN in env")
        return

    print("Starting Fyers Data WebSocket...")
    print("Client ID:", FYERS_CLIENT_ID)
    fyers = fyersModel.FyersDataSocket(
        access_token=f"{FYERS_CLIENT_ID}:{FYERS_ACCESS_TOKEN}",
        log_path="",
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open,
    )

    fyers.connect()
    # main thread alive ठेवण्यासाठी
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping WS...")
        fyers.close()


if __name__ == "__main__":
    start_ws()
