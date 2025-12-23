# ============================================================
# RajanTradeAutomation – FINAL MAIN.PY (PRODUCTION SAFE)
# Flask + FYERS WS + Google Sheets (WebApp.gs)
# ============================================================

import os
import time
import threading
from datetime import datetime
import requests
from flask import Flask, request, jsonify
from fyers_apiv3.FyersWebsocket import data_ws

# ============================================================
# ENVIRONMENT VARIABLES (LOCKED)
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
# SAFE TIME PARSER
# ============================================================

def parse_time(val):
    if not val:
        return None
    try:
        if "T" in val:
            return datetime.fromisoformat(val.replace("Z", "")).time()
        if len(val.split(":")) == 2:
            return datetime.strptime(val, "%H:%M").time()
        return datetime.strptime(val, "%H:%M:%S").time()
    except Exception:
        return None


def now_time():
    return datetime.now().time()

# ============================================================
# WEBAPP COMMUNICATION (POST ONLY)
# ============================================================

def call_webapp(action, payload=None, timeout=10):
    if payload is None:
        payload = {}
    try:
        return requests.post(
            WEBAPP_URL,
            json={"action": action, "payload": payload},
            timeout=timeout
        ).json()
    except Exception:
        return None


def load_settings():
    global SETTINGS, SETTINGS_LOADED
    res = call_webapp("getSettings", {})
    if res and res.get("ok"):
        SETTINGS = res.get("settings", {})
        SETTINGS_LOADED = True
        print("✅ Settings loaded from Google Sheet")
    else:
        print("⚠️ Settings not loaded yet")

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
    print("❌ WS error:", err)


def on_close():
    print("⚠️ WS closed")

# ============================================================
# FYERS WS INIT (CONNECT ONLY ONCE)
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
    try:
        ws.connect()
    except Exception as e:
        print("WS start failed:", e)

# ============================================================
# ENGINE LOOP (TIME DRIVEN)
# ============================================================

def engine_loop():
    print("▶ Engine loop started")

    while True:
        if not SETTINGS_LOADED:
            time.sleep(1)
            continue

        tick_start = parse_time(SETTINGS.get("TICK_START_TIME", "11:10:00"))
        bias_time  = parse_time(SETTINGS.get("BIAS_TIME_INFO", "11:20:05"))
        stop_time  = parse_time(SETTINGS.get("AUTO_SQUAREOFF_TIME", "15:15"))

        now = now_time()

        if tick_start and now >= tick_start:
            pass  # tick capture via WS

        if bias_time and now >= bias_time:
            call_webapp("pushState", {
                "items": [{"key": "BIAS_CHECK_DONE", "value": "TRUE"}]
            })

        if stop_time and now >= stop_time:
            print("⛔ Stop time reached")
            break

        time.sleep(1)

# ============================================================
# FLASK APP (LOCKED ROUTES)
# ============================================================

app = Flask(__name__)

@app.route("/")
def root():
    return "RajanTradeAutomation backend LIVE ✅"

@app.route("/ping")
def ping():
    return "PONG"

@app.route("/getSettings")
def api_get_settings():
    return jsonify({"ok": True, "settings": SETTINGS})

@app.route("/fyers-redirect")
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
# MAIN ENTRY
# ============================================================

if __name__ == "__main__":
    print("🚀 Starting RajanTradeAutomation")

    load_settings()

    threading.Thread(target=start_ws, daemon=True).start()
    threading.Thread(target=engine_loop, daemon=True).start()

    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
