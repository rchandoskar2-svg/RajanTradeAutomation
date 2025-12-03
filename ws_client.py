import os
import json
import time
import threading
import websocket  # pip install websocket-client

# ------------------------------
# ENV VARIABLES
# ------------------------------
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

# उदाहरण symbol – नंतर list वाढवू
SYMBOLS = [
    "NSE:SBIN-EQ",
    "NSE:RELIANCE-EQ",
]

# Fyers data WebSocket endpoint (v3 style)
WS_URL = "wss://api-t1.fyers.in/data/ws/v3"  # if this fails, we'll adjust to /data/ws/v2


def on_message(ws, message):
    try:
        data = json.loads(message)
    except Exception:
        print("RAW MSG:", message)
        return

    # Tick structure Fyers कडून थोडा बदलू शकतो, पण साधारण:
    # { "symbol": "NSE:SBIN-EQ", "ltp": 123.45, "vol": ..., ... }
    print("TICK:", data)


def on_error(ws, error):
    print("WS ERROR:", error)


def on_close(ws, close_status_code, close_msg):
    print("WS CLOSED:", close_status_code, close_msg)


def on_open(ws):
    print("WS OPENED, sending auth + subscription...")

    # 1) Auth payload – काही implementations मध्ये header मध्ये token जातो,
    # काहींमध्ये login payload. इथे basic data-token format वापरतो:
    auth_token = f"{CLIENT_ID}:{ACCESS_TOKEN}"

    # 2) Subscription payload – mode: 'quote' / 'full' इ. (depends on plan)
    payload = {
        "T": "SUB_L2",           # किंवा "SUB_MW"/"SUB_SYMBOL" – plan नुसार fine-tune करु
        "AUTH": auth_token,
        "SYMBOLS": ",".join(SYMBOLS),
    }

    try:
        ws.send(json.dumps(payload))
        print("SUB SENT:", payload)
    except Exception as e:
        print("WS SEND ERROR:", str(e))


def run_ws():
    if not CLIENT_ID or not ACCESS_TOKEN:
        print("❌ Missing CLIENT_ID or ACCESS_TOKEN in environment!")
        return

    while True:
        try:
            ws = websocket.WebSocketApp(
                WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            ws.run_forever(ping_interval=20, ping_timeout=10)
        except Exception as e:
            print("WS CONNECT ERROR:", str(e))

        print("Reconnecting in 5 seconds...")
        time.sleep(5)


if __name__ == "__main__":
    print("Starting Fyers Tick WebSocket client...")
    run_ws()
