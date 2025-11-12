# ===========================================================
# 🚀 RajanTradeAutomation – Phase 2.3.5 (Stable Sync + SmartCount Patch)
# Author: Rajan Chandoskar & GPT-5 Assistant
# ===========================================================

from flask import Flask, request, jsonify
import os, json, requests, time, traceback

app = Flask(__name__)
APP_NAME = "RajanTradeAutomation"

# ---------- Environment Variables ----------
WEBAPP_EXEC_URL = os.getenv("WEBAPP_EXEC_URL")        # Google Apps Script WebApp exec URL
CHARTINK_TOKEN  = os.getenv("CHARTINK_TOKEN", "RAJAN123")
SCANNER_NAME    = os.getenv("SCANNER_NAME", "Rocket Rajan Scanner")
SCANNER_URL     = os.getenv("SCANNER_URL", "")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
INTERVAL_SECS   = int(os.getenv("INTERVAL_SECS", "1800"))
TEST_TOKEN      = os.getenv("TEST_TOKEN", "TEST123")

# ===========================================================
# 🔹 Helper: Telegram Notify
# ===========================================================
def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram not configured.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print("Telegram send failed:", r.text)
    except Exception as e:
        print("Telegram error:", e)

# ===========================================================
# 🔹 Helper: Call Google WebApp
# ===========================================================
def gs_post(payload: dict):
    if not WEBAPP_EXEC_URL:
        raise Exception("WEBAPP_EXEC_URL not configured in environment")
    r = requests.post(WEBAPP_EXEC_URL, json=payload, timeout=30)
    r.raise_for_status()
    try:
        return r.json()
    except:
        return {"ok": False, "raw": r.text}

# ===========================================================
# 🔹 Health Check
# ===========================================================
@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "app": APP_NAME,
        "ts": int(time.time()),
        "mode": "LIVE" if "LIVE" in APP_NAME.upper() else "PAPER"
    })

# ===========================================================
# 🔹 Chartink Alert Receiver (SmartCount Patch)
# ===========================================================
@app.post("/chartink-alert")
def chartink_alert():
    try:
        token = request.args.get("token")
        if CHARTINK_TOKEN and token and token != CHARTINK_TOKEN:
            return jsonify({"ok": False, "error": "Invalid Chartink token"}), 403

        data = request.get_json(force=True, silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "Invalid JSON payload"}), 400

        # Enrich payload with scanner info
        data["scanner_name"] = SCANNER_NAME
        data["scanner_url"]  = SCANNER_URL

        # 🧠 Primary detection logic
        detected = 0
        try:
            detected = len(data.get("stocks", []))
        except Exception:
            detected = 0

        # ✅ PATCH: Chartink dict/string handling fix
        try:
            stocks_field = data.get("stocks", [])
            if isinstance(stocks_field, dict):
                detected = len(stocks_field.keys())
            elif isinstance(stocks_field, str):
                detected = len([s for s in stocks_field.split(",") if s.strip()])
        except Exception:
            detected = 0

        # Forward to Google WebApp
        res = gs_post({"action": "chartink_import", "payload": data})

        send_telegram(
            f"📥 Chartink alert received — forwarded to WebApp.\n✅ {detected} stocks detected."
        )
        return jsonify({"ok": True, "webapp_response": res})

    except Exception as e:
        err = traceback.format_exc()
        send_telegram(f"❌ Render webhook error:\n{e}")
        try:
            gs_post({"action": "phase22_error", "payload": {"message": str(e)}})
        except:
            pass
        return jsonify({"ok": False, "error": str(e)}), 500

# ===========================================================
# 🔹 Manual Test Routes
# ===========================================================
@app.get("/test-connection")
def test_connection():
    try:
        if not WEBAPP_EXEC_URL:
            return "WEBAPP_EXEC_URL missing in environment", 500
        r = requests.post(WEBAPP_EXEC_URL, json={"action": "get_settings"}, timeout=25)
        return r.text, 200, {"Content-Type": "application/json"}
    except Exception as e:
        return traceback.format_exc(), 500

@app.get("/test-telegram")
def test_telegram():
    try:
        send_telegram("✅ Telegram test successful — RajanTradeAutomation Render connected.")
        return jsonify({"ok": True, "msg": "Telegram sent"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ===========================================================
# 🔹 Entry Point
# ===========================================================
if __name__ == "__main__":
    print("🚀 RajanTradeAutomation Render Service starting...")
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
