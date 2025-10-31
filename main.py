import os, time, json, requests
from threading import Thread
from flask import Flask

app = Flask(__name__)

@app.get("/")
def home():
    return "✅ Rajan Render Bot is Alive!"

# Environment variables
WEBAPP_URL = os.getenv("WEBAPP_URL")
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
INTERVAL_SECS = int(os.getenv("INTERVAL_SECS", "1800"))  # default 30 मिनिटे

def send_telegram(text: str):
    if not TOKEN or not CHAT_ID:
        print("⚠️ Telegram credentials missing")
        return
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=10)
    except Exception as e:
        print("Telegram error:", e)

def post_to_webapp(action: str, data: dict):
    if not WEBAPP_URL:
        send_telegram("⚠️ WEBAPP_URL missing")
        return False, "no_url"
    try:
        headers = {"Content-Type": "application/json"}
        payload = {"action": action, "data": data or {}}
        r = requests.post(WEBAPP_URL, headers=headers, data=json.dumps(payload), timeout=20)
        ok = (r.status_code == 200)
        return ok, (r.text if r.text else r.status_code)
    except Exception as e:
        return False, str(e)

def cycle_once():
    ok, resp = post_to_webapp("updateLowWindow", {"source": "render"})
    if ok:
        send_telegram("✅ Render → WebApp call OK (updateLowWindow).")
    else:
        send_telegram(f"❌ WebApp call failed: {resp}")

def background_loop():
    send_telegram("🚀 Rajan Bot Started on Render!")
    cycle_once()
    while True:
        time.sleep(INTERVAL_SECS)
        cycle_once()

def start_background():
    t = Thread(target=background_loop, daemon=True)
    t.start()

if __name__ == "__main__":
    start_background()
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
