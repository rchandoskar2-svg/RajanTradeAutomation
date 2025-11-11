# ===========================================================
# 🚀 RajanTradeAutomation – Phase 2.3.1 (SmartCountSync + Chunked Transfer)
# Author: Rajan Chandoskar & GPT-5 Assistant
# ===========================================================

from flask import Flask, request, jsonify
import os, json, requests, time, traceback, math

app = Flask(__name__)
APP_NAME = "RajanTradeAutomation"

# ---------- Environment Variables ----------
WEBAPP_EXEC_URL = os.getenv("WEBAPP_EXEC_URL")     # Google Apps Script WebApp URL
CHARTINK_TOKEN  = os.getenv("CHARTINK_TOKEN", "RAJAN123")
SCANNER_NAME    = os.getenv("SCANNER_NAME", "Rocket Rajan Scanner")
SCANNER_URL     = os.getenv("SCANNER_URL", "")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
INTERVAL_SECS   = int(os.getenv("INTERVAL_SECS", "1800"))
TEST_TOKEN      = os.getenv("TEST_TOKEN", "TEST123")

# ---------- Helper : Telegram Notify ----------
def send_telegram(text: str):
    """Send message to Telegram"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram not configured.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
        if r.status_code != 200:
            print("Telegram send failed:", r.text)
    except Exception as e:
        print("Telegram error:", e)

# ---------- Helper : Call Google WebApp ----------
def gs_post(payload: dict):
    if not WEBAPP_EXEC_URL:
        raise Exception("WEBAPP_EXEC_URL not configured in environment")
    r = requests.post(WEBAPP_EXEC_URL, json=payload, timeout=45)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "raw": r.text}

# ---------- Health Check ----------
@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "app": APP_NAME,
        "ts": int(time.time()),
        "mode": "LIVE" if "LIVE" in APP_NAME.upper() else "PAPER"
    })

# ---------- Chartink Alert Receiver (Patched) ----------
@app.post("/chartink-alert")
def chartink_alert():
    """
    Receives incoming alerts from Chartink,
    validates token, and forwards in manageable chunks to Google WebApp.
    """
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

        stocks = data.get("stocks", [])
        detected = len(stocks)
        if detected == 0:
            send_telegram("⚠️ Chartink alert received but no stocks found.")
            return jsonify({"ok": False, "msg": "No stocks"})

        # 🟢 Smart Chunked Transfer — 500 stocks per chunk
        CHUNK = 500
        total_imported = 0
        chunks = math.ceil(detected / CHUNK)

        for i in range(0, detected, CHUNK):
            batch = stocks[i:i + CHUNK]
            payload = {
                "action": "chartink_import",
                "payload": {
                    "stocks": batch,
                    "detected_count": detected,
                    "scanner_name": SCANNER_NAME,
                    "scanner_url": SCANNER_URL
                }
            }
            try:
                r = requests.post(WEBAPP_EXEC_URL, json=payload, timeout=45)
                imported = 0
                try:
                    imported = r.json().get("count", 0)
                except Exception:
                    pass
                total_imported += imported
                time.sleep(1)  # safety delay between chunks
            except Exception as e:
                send_telegram(f"⚠️ Chunk error: {i//CHUNK+1}/{chunks} → {e}")

        diff = detected - total_imported
        msg = f"📊 SmartCountSync\nDetected: {detected}\nImported: {total_imported}\nDiff: {diff}"
        send_telegram(msg)

        return jsonify({"ok": True, "detected": detected, "imported": total_imported, "diff": diff})

    except Exception as e:
        err = traceback.format_exc()
        send_telegram(f"❌ Render webhook error:\n{e}")
        try:
            gs_post({"action": "phase22_error", "payload": {"message": str(e)}})
        except Exception:
            pass
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------- Manual test routes ----------
@app.get("/test-connection")
def test_connection():
    try:
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

# ---------- Entry Point ----------
if __name__ == "__main__":
    print("🚀 RajanTradeAutomation Render Service starting...")
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
