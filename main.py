import os, time, json, requests
from flask import Flask, request, jsonify
from threading import Thread

# ================================================================
# 🚀 RajanTradeAutomation - Render Live Version (Phase 1 + 2)
# Flask + Telegram + Google WebApp + Chartink Webhook
# ================================================================

app = Flask(__name__)

# -------------------------
# Environment (Render variables)
# -------------------------
WEBAPP_URL       = os.getenv("WEBAPP_URL")                 # Google Apps Script WebApp URL
TOKEN            = os.getenv("TELEGRAM_TOKEN")             # Telegram BOT token
CHAT_ID          = os.getenv("TELEGRAM_CHAT_ID")           # Telegram chat id
INTERVAL_SECS    = int(os.getenv("INTERVAL_SECS", "1800")) # default 30 minutes
CHARTINK_TOKEN   = os.getenv("CHARTINK_TOKEN", "")         # security token for webhook
TEST_TOKEN       = os.getenv("TEST_TOKEN", "")             # for /test/fake-alert
SCANNER_NAME     = os.getenv("SCANNER_NAME", "")           # scanner name
SCANNER_URL      = os.getenv("SCANNER_URL", "")            # scanner url

# -------------------------
# Utils
# -------------------------
def send_telegram(text: str):
    """Send Telegram message (short, no secrets)."""
    if not TOKEN or not CHAT_ID:
        print("⚠️ Telegram credentials missing")
        return
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=10)
    except Exception as e:
        print("Telegram error:", e)


def post_to_webapp(action: str, data: dict):
    """POST to Google Apps Script WebApp."""
    if not WEBAPP_URL:
        send_telegram("⚠️ WEBAPP_URL missing")
        return False, "no_url"
    try:
        headers = {"Content-Type": "application/json"}
        payload = {"action": action, "data": data or {}}
        r = requests.post(WEBAPP_URL, headers=headers, data=json.dumps(payload), timeout=20)
        ok = r.status_code == 200
        return ok, (r.text if r.text else r.status_code)
    except Exception as e:
        return False, str(e)


# -------------------------
# Background Loop (Phase 1)
# -------------------------
def cycle_once():
    """Single trigger cycle — update morning window lows."""
    ok, resp = post_to_webapp("updateLowWindow", {"source": "render"})
    if ok:
        send_telegram("✅ Render → WebApp call OK (updateLowWindow).")
    else:
        send_telegram(f"❌ WebApp call failed: {resp}")


def run_loop():
    """Repeated keep-alive + routine jobs."""
    send_telegram("🚀 Rajan Bot Started on Render!")
    while True:
        cycle_once()
        time.sleep(INTERVAL_SECS)


def start_background_loop():
    t = Thread(target=run_loop)
    t.daemon = True
    t.start()


# -------------------------
# Flask Routes
# -------------------------
@app.route("/")
def home():
    return "✅ Rajan Render Bot is Alive!", 200


@app.route("/health")
def health():
    info = {"status": "ok", "ts": int(time.time())}
    if SCANNER_NAME:
        info["scanner"] = SCANNER_NAME
    return jsonify(info), 200


# ================================================================
# ⚡ Chartink Webhook Receiver (Phase 2 - Enhanced)
# ================================================================
@app.post("/chartink-alert")
def chartink_alert():
    # Token guard (optional)
    if CHARTINK_TOKEN:
        if request.args.get("token", "") != CHARTINK_TOKEN:
            return jsonify({"ok": False, "err": "unauthorized"}), 401
            # --- RAW BODY DEBUG LOG ---
    try:
        raw_body = request.data.decode("utf-8", errors="ignore")
        print("\n================ RAW CHARTINK BODY ================")
        print(raw_body)
        print("===================================================\n")
        send_telegram("📩 Raw alert captured — check Render logs for details.")
    except Exception as e:
        print("Error reading raw body:", e)

    payload = request.get_json(force=True, silent=True) or {}
    symbols = []

    # 1️⃣ Handle array-based formats
    for key in ("stocks", "symbols"):
        v = payload.get(key)
        if isinstance(v, list):
            symbols = [x.strip().upper() for x in v if str(x).strip()]
            if symbols:
                break

    # 2️⃣ Handle string-based formats
    if not symbols:
        for key in ("stocks_str", "symbols_str", "text"):
            v = payload.get(key)
            if isinstance(v, str) and v.strip():
                symbols = [x.strip().upper() for x in v.replace("\n", ",").split(",") if x.strip()]
                if symbols:
                    break

    # 3️⃣ Handle raw plain text fallback
    if not symbols and isinstance(payload, str):
        symbols = [x.strip().upper() for x in payload.split(",") if x.strip()]

    # 4️⃣ Handle HTML/Email text fallback (if email-like body)
    if not symbols and "body" in payload:
        text = payload["body"]
        if isinstance(text, str):
            symbols = [x.strip().upper() for x in text.replace("\n", ",").split(",") if x.strip()]

    if not symbols:
        send_telegram("⚠️ Chartink alert received but no stock symbols found.")
        return jsonify({"ok": False, "err": "no symbols"}), 400

    # ✅ Send Telegram update
    msg = f"📊 Chartink alert — {len(symbols)} symbols received:\n" + ", ".join(symbols[:10])
    send_telegram(msg)

    # ✅ Send to Google WebApp
    post_to_webapp("chartink_import", {
        "symbols": symbols,
        "scanner": SCANNER_NAME,
        "scanner_url": SCANNER_URL
    })

    return jsonify({"ok": True, "count": len(symbols), "symbols": symbols}), 200


# ================================================================
# 🧪 Manual Test Route
# ================================================================
@app.post("/test/fake-alert")
def fake_alert():
    if TEST_TOKEN and request.args.get("token", "") != TEST_TOKEN:
        return jsonify({"ok": False, "err": "unauthorized"}), 401

    data = request.get_json(force=True, silent=True) or {"stocks": ["SBIN", "TCS", "INFY"]}
    with app.test_request_context("/chartink-alert", method="POST", json=data):
        return chartink_alert()


# ================================================================
# 🧠 Entry Point
# ================================================================
if __name__ == "__main__":
    start_background_loop()
    print("✅ Background loop started. Flask server now running...")
    app.run(host="0.0.0.0", port=10000)
