import os, time, json, requests
from flask import Flask, jsonify
from threading import Thread

# ================================================================
# 🚀 RajanTradeAutomation - Render Live Version
# Flask app with /health endpoint for UptimeRobot ping protection
# ================================================================

app = Flask(__name__)

# 🟢 Home Route (For manual check)
@app.route('/')
def home():
    return "✅ Rajan Render Bot is Alive!"

# 🩺 Health Check Route (For UptimeRobot)
@app.route('/health')
def health():
    return jsonify({"status": "ok"}), 200


# ================================================================
# 🔧 Core Bot Logic
# ================================================================

WEBAPP_URL = os.getenv("WEBAPP_URL")
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
INTERVAL_SECS = int(os.getenv("INTERVAL_SECS", "1800"))  # default 30 minutes


def send_telegram(text: str):
    """Send Telegram message"""
    if not TOKEN or not CHAT_ID:
        print("⚠️ Telegram credentials missing")
        return
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=10)
    except Exception as e:
        print("Telegram error:", e)


def post_to_webapp(action: str, data: dict):
    """Send POST request to Google WebApp"""
    if not WEBAPP_URL:
        send_telegram("⚠️ WEBAPP_URL missing")
        return False, "no_url"
    try:
        headers = {"Content-Type": "application/json"}
        payload = {"action": action, "data": data or {}}
        r = requests.post(WEBAPP_URL,
                          headers=headers,
                          data=json.dumps(payload),
                          timeout=20)
        ok = r.status_code == 200
        return ok, (r.text if r.text else r.status_code)
    except Exception as e:
        return False, str(e)


def cycle_once():
    """Single trigger cycle"""
    ok, resp = post_to_webapp("updateLowWindow", {"source": "render"})
    if ok:
        send_telegram("✅ Render → WebApp call OK (updateLowWindow).")
    else:
        send_telegram(f"❌ WebApp call failed: {resp}")


def run_loop():
    """Repeated task loop"""
    send_telegram("🚀 Rajan Bot Started on Render!")
    while True:
        cycle_once()
        time.sleep(INTERVAL_SECS)


def start_background_loop():
    t = Thread(target=run_loop)
    t.daemon = True
    t.start()


# ================================================================
# 🧠 Main Entry Point
# ================================================================
if __name__ == "__main__":
    start_background_loop()
    print("✅ Background loop started. Flask server now running...")
    app.run(host="0.0.0.0", port=10000)
