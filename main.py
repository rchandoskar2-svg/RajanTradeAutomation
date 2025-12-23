# ============================================================
# RajanTradeAutomation – FINAL main.py (LOCKED BASE)
# Flask + FYERS WS + Settings-driven Engine
# ============================================================

from flask import Flask, request, jsonify
import os, time, threading, requests
from datetime import datetime, time as dtime
from fyers_apiv3.FyersWebsocket import data_ws

# ============================================================
# ENV (Render)
# ============================================================
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY", "").strip()
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI", "").strip()
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()

if not WEBAPP_URL:
    raise Exception("WEBAPP_URL missing")

# ============================================================
# FLASK BASE (LOCKED)
# ============================================================
app = Flask(__name__)

@app.route("/")
def root():
    return "RajanTradeAutomation is LIVE ✅", 200

@app.route("/ping")
def ping():
    return "PONG", 200

@app.route("/getSettings")
def get_settings():
    return jsonify(call_webapp("getSettings"))

@app.route("/fyers-redirect")
def fyers_redirect():
    auth_code = request.args.get("auth_code", "")
    return f"""
    <h3>FYERS AUTH CODE</h3>
    <textarea rows="5" cols="100">{auth_code}</textarea>
    """

# ============================================================
# HELPERS
# ============================================================
def call_webapp(action, payload=None, timeout=10):
    if payload is None:
        payload = {}
    try:
        r = requests.post(
            WEBAPP_URL,
            json={"action": action, "payload": payload},
            timeout=timeout
        )
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def parse_time_safe(val: str):
    """
    Accepts:
    - HH:MM
    - HH:MM:SS
    - ISO datetime
    """
    if not val:
        return None
    try:
        if "T" in val:
            return datetime.fromisoformat(val).time()
        parts = val.split(":")
        if len(parts) == 2:
            return dtime(int(parts[0]), int(parts[1]))
        if len(parts) == 3:
            return dtime(int(parts[0]), int(parts[1]), int(parts[2]))
    except:
        return None
    return None

def now_time():
    return datetime.now().time()

# ============================================================
# SETTINGS CACHE
# ============================================================
SETTINGS = {}
SETTINGS_TS = 0

def refresh_settings():
    global SETTINGS, SETTINGS_TS
    res = call_webapp("getSettings")
    if res.get("ok"):
        SETTINGS = res.get("settings", {})
        SETTINGS_TS = time.time()

def get_setting_time(key):
    return parse_time_safe(SETTINGS.get(key, ""))

# ============================================================
# FYERS WS
# ============================================================
tick_cache = {}
ws_connected = False

def on_ws_open():
    global ws_connected
    ws_connected = True
    print("FYERS WS connected")

def on_ws_message(msg):
    try:
        sym = msg.get("symbol")
        ltp = msg.get("ltp")
        if sym and ltp:
            tick_cache[sym] = ltp
    except:
        pass

def on_ws_error(err):
    print("WS error:", err)

ws = data_ws.FyersDataSocket(
    access_token=FYERS_ACCESS_TOKEN,
    on_connect=on_ws_open,
    on_message=on_ws_message,
    on_error=on_ws_error,
    reconnect=True
)

def ws_runner():
    while True:
        try:
            ws.connect()
        except:
            time.sleep(5)

# ============================================================
# ENGINE LOOP (SAFE)
# ============================================================
def engine_loop():
    refresh_settings()
    print("Engine started")

    while True:
        try:
            if time.time() - SETTINGS_TS > 60:
                refresh_settings()

            tick_start = get_setting_time("TICK_START_TIME")
            bias_time  = get_setting_time("BIAS_TIME")
            stop_time  = get_setting_time("TRADE_STOP_TIME")

            now = now_time()

            if tick_start and now < tick_start:
                time.sleep(1)
                continue

            # 🔜 पुढचे logic: candle, sector, signal
            # (हे logic आधीच वेगळ्या files मध्ये आहे – unchanged)

            if stop_time and now >= stop_time:
                print("Trade stop time reached")
                break

            time.sleep(1)

        except Exception as e:
            print("ENGINE ERROR:", e)
            time.sleep(2)

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    threading.Thread(target=ws_runner, daemon=True).start()
    threading.Thread(target=engine_loop, daemon=True).start()

    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
