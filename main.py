# ============================================================
# RajanTradeAutomation – FINAL MAIN.PY (LOCKED & FIXED)
# Render + Flask + FYERS WebSocket
# ============================================================

import os
import time
import threading
from datetime import datetime, time as dtime
import requests
from flask import Flask, request, jsonify
from fyers_apiv3.FyersWebsocket import data_ws

# ============================================================
# ENVIRONMENT VARIABLES (DO NOT CHANGE)
# ============================================================

WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY", "").strip()
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

if not WEBAPP_URL or not FYERS_ACCESS_TOKEN:
    raise Exception("Missing required ENV variables")

# ============================================================
# GLOBAL STATE
# ============================================================

SETTINGS = {}
SETTINGS_LOADED = False

tick_cache = {}
ws_connected = False

# ============================================================
# TIME HELPERS (SAFE PARSING)
# ============================================================

def parse_time(value: str) -> dtime:
    """
    Accepts:
    - HH:MM
    - HH:MM:SS
    - ISO datetime → extracts time
    """
    if not value:
        return None

    value = value.strip()

    try:
        if "T" in value:
            return datetime.fromisoformat(value.replace("Z", "")).time()
        if len(value.split(":")) == 2:
            return datetime.strptime(value, "%H:%M").time()
        return datetime.strptime(value, "%H:%M:%S").time()
    except Exception:
        return None


def now_time():
    return datetime.now().time()


# ============================================================
# WEBAPP COMMUNICATION
# ============================================================

def call_webapp(action, payload=None, timeout=10):
    if payload is None:
        payload = {}
    try:
        requests.post(
            WEBAPP_URL,
            json={"action": action, "payload": payload},
            timeout=timeout
        )
    except Exception:
        pass


def load_settings():
    global SETTINGS, SETTINGS_LOADED
    try:
        r = requests.get(f"{WEBAPP_URL}?action=getSettings", timeout=10)
        data = r.json()
        if data.get("ok"):
            SETTINGS = data.get("settings", {})
            SETTINGS_LOADED = True
            print("✔ Settings loaded")
    except Exception as e:
        print("Settings load failed:", e)


# ============================================================
# FYERS WEBSOCKET CALLBACKS
# ============================================================

def on_message(msg):
    symbol = msg.get("symbol")
    ltp = msg.get("ltp")
    vol = msg.get("vol_traded_today")

    if not symbol or ltp is None:
        return

    tick_cache[symbol] = {
        "ltp": ltp,
        "volume": vol,
        "time": datetime.now().isoformat()
    }


def on_connect():
    global ws_connected
    ws_connected = True
    print("✅ FYERS WS connected")


def on_error(err):
    print("WS error:", err)


def on_close():
    print("WS closed")


# ============================================================
# FYERS WS INIT (IMPORTANT: CONNECT ONLY ONCE)
# ============================================================

ws = data_ws.FyersDataSocket(
    access_token=FYERS_ACCESS_TOKEN,
    on_message=on_message,
    on_connect=on_connect,
    on_error=on_error,
    on_close=on_close,
    reconnect=True
)


def start_ws():
    # ⚠️ NO while loop here – VERY IMPORTANT
    try:
        ws.connect()
    except Exception as e:
        print("WS start error:", e)


# ============================================================
# ENGINE LOOP (TIME SAFE)
# ============================================================

def engine_loop():
    print("▶ Engine loop started")

    while True:
        if not SETTINGS_LOADED:
            time.sleep(1)
            continue

        tick_start = parse_time(SETTINGS.get("TICK_START_TIME", "10:39:00"))
        bias_time  = parse_time(SETTINGS.get("BIAS_TIME_INFO", "10:50:05"))
        stop_time  = parse_time(SETTINGS.get("AUTO_SQUAREOFF_TIME", "15:15"))

        now = now_time()

        # Silent tick window
        if tick_start and now >= tick_start:
            pass  # tick collection already happening via WS

        # Bias snapshot trigger
        if bias_time and now >= bias_time:
            call_webapp("pushState", {
                "items": [{"key": "BIAS_CHECK_DONE", "value": "TRUE"}]
            })

        # Stop engine after squareoff
        if stop_time and now >= stop_time:
            print("⛔ Stop time reached")
            break

        time.sleep(1)


# ============================================================
# FLASK APP (LOCKED BASE – DO NOT REMOVE ROUTES)
# ============================================================

app = Flask(__name__)

@app.route("/", methods=["GET"])
def root():
    return "RajanTradeAutomation backend LIVE ✅", 200


@app.route("/ping", methods=["GET"])
def ping():
    return "PONG", 200


@app.route("/getSettings", methods=["GET"])
def api_get_settings():
    return jsonify({"ok": True, "settings": SETTINGS})


@app.route("/fyers-redirect", methods=["GET"])
def fyers_redirect():
    status = request.args.get("s", "")
    auth_code = request.args.get("auth_code", "")
    state = request.args.get("state", "")

    return f"""
    <h3>Fyers Redirect</h3>
    <p>Status: {status}</p>
    <p>State: {state}</p>
    <textarea rows="5" cols="120">{auth_code}</textarea>
    """


# ============================================================
# MAIN ENTRY (ORDER MATTERS)
# ============================================================

if __name__ == "__main__":
    print("🚀 Starting RajanTradeAutomation")

    load_settings()

    # Start WS ONCE
    threading.Thread(target=start_ws, daemon=True).start()

    # Start engine loop
    threading.Thread(target=engine_loop, daemon=True).start()

    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
