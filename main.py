# ===========================================================
# RajanTradeAutomation – Phase 2 (Stable + Clean Sync Version)
# ===========================================================

from flask import Flask, request, jsonify
import os, json, requests, time, traceback

app = Flask(__name__)
APP_NAME = "RajanTradeAutomation"

# ---------- Environment ----------
WEBAPP_EXEC_URL = os.getenv("WEBAPP_EXEC_URL")  # Google Apps Script WebApp exec URL
CHARTINK_TOKEN  = os.getenv("CHARTINK_TOKEN", "RAJAN123")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ---------- Helper: Post to Google WebApp ----------
def gs_post(payload):
    if not WEBAPP_EXEC_URL:
        raise Exception("WEBAPP_EXEC_URL not configured")
    r = requests.post(WEBAPP_EXEC_URL, json=payload, timeout=25)
    r.raise_for_status()
    try:
        return r.json()
    except:
        return {"ok": True, "raw": r.text}

# ---------- Health Check ----------
@app.get("/health")
def health():
    return jsonify({"ok": True, "app": APP_NAME, "timestamp": int(time.time())})

# ---------- Manual Test Connection ----------
@app.get("/test-connection")
def test_connection():
    """Check Render → Google WebApp connectivity"""
    try:
        if not WEBAPP_EXEC_URL:
            return "WEBAPP_EXEC_URL missing in environment", 500
        r = requests.post(WEBAPP_EXEC_URL, json={"action": "get_settings"}, timeout=25)
        return r.text, 200, {"Content-Type": "application/json"}
    except Exception as e:
        return traceback.format_exc(), 500

# ---------- Chartink Webhook ----------
@app.post("/chartink-alert")
def chartink_alert():
    try:
        token = request.args.get("token")
        if CHARTINK_TOKEN and token and token != CHARTINK_TOKEN:
            return jsonify({"ok": False, "error": "Invalid token"}), 403

        # --- Get and clean payload ---
        data = request.get_json(force=True, silent=True) or {}
        stocks = []

        # Flexible input formats
        if isinstance(data, dict) and "stocks" in data:
            stocks = data["stocks"]
        elif isinstance(data, list):
            stocks = data
        elif isinstance(data, str):
            stocks = [{"symbol": s.strip()} for s in data.split(",") if s.strip()]

        # Filter valid symbols only
        clean_stocks = []
        for s in stocks:
            if isinstance(s, dict) and "symbol" in s:
                sym = str(s["symbol"]).strip().upper()
                if sym and len(sym) < 15:
                    clean_stocks.append({"symbol": sym})

        valid_count = len(clean_stocks)

        # --- Forward to Google WebApp ---
        payload = {"action": "chartink_import", "payload": {"stocks": clean_stocks, **data}}
        res = gs_post(payload)

        # --- Telegram Notification ---
        if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
            msg = f"📥 Chartink alert received — forwarded to WebApp.\n✅ {valid_count} stocks detected."
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
                timeout=10
            )

        return jsonify({"ok": True, "forwarded": True, "count": valid_count, "sheet": res})

    except Exception as e:
        try:
            gs_post({"action": "phase22_error", "message": str(e)})
        except:
            pass
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------- Entry ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
