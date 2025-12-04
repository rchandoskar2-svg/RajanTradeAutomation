import os
import json
import time
import websocket
from fyers_apiv3 import fyersModel

CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

FY_WS_URL = "wss://api.fyers.in/socket/v3/data"
SYMBOLS = ["NSE:SBIN-EQ", "NSE:RELIANCE-EQ"]


def on_message(ws, message):
    try:
        data = json.loads(message)
        print("WS:", data)
    except:
        print("RAW:", message)


def on_error(ws, error):
    print("WS ERROR:", error)


def on_close(ws, code, msg):
    print("WS CLOSED", code, msg)


def on_open(ws):
    print("WS OPENED… subscribing…")

    sub = {
        "symbol": SYMBOLS,
        "type": "symbolUpdate"
    }
    ws.send(json.dumps(sub))
    print("SUB SENT:", sub)


def ws_loop():
    if not CLIENT_ID or not ACCESS_TOKEN:
        print("❌ Missing CLIENT_ID or ACCESS_TOKEN")
        return

    headers = [
        f"Authorization: Bearer {ACCESS_TOKEN}",
        f"client_id: {CLIENT_ID}",
    ]

    while True:
        try:
            print("Connecting WS →", FY_WS_URL)
            ws = websocket.WebSocketApp(
                FY_WS_URL,
                header=headers,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            ws.run_forever(ping_interval=20, ping_timeout=10)
        except Exception as e:
            print("WS LOOP ERROR:", e)

        print("Reconnecting in 5 sec…")
        time.sleep(5)


if __name__ == "__main__":
    ws_loop()
