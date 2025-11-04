# ===========================================================
# RajanTradeAutomation – Phase 2 (Stable restore)
# ===========================================================

from flask import Flask, request, jsonify
import os, json, requests, time

app = Flask(__name__)
APP_NAME = "RajanTradeAutomation"

# ---------- Environment ----------
WEBAPP_EXEC_URL = os.getenv("WEBAPP_EXEC_URL")  # Google Apps Script WebApp exec URL
CHARTINK_TOKEN  = os.getenv("CHARTINK_TOKEN", "RAJAN123")

# ---------- Helper to call Google WebApp ----------
def gs_post(payload):
    if not WEBAPP_EXEC_URL:
        raise Exception("WEBAPP_EXEC_URL not configured")
    r = requests.post(WEBAPP_EXEC_URL, json=payload, timeout=25)
    r.raise_for_status()
    return r.json()

# ---------- Health Check ----------
@app.get("/health")
def health():
    return jsonify({"ok": True, "app": APP_NAME, "ts": int(time.time())})

# ---------- Chartink Webhook ----------
@app.post("/chartink-alert")
def chartink_alert():
    try:
        token = request.args.get("token")
        if CHARTINK_TOKEN and token and token != CHARTINK_TOKEN:
            return jsonify({"ok": False, "error": "Invalid token"}), 403

        data = request.get_json(force=True, silent=True) or {}
        # forward to Google WebApp (phase-2 style)
        res = gs_post({"action": "chartink_import", "payload": data})
        return jsonify({"ok": True, "sheet": res})
    except Exception as e:
        try:
            gs_post({"action": "phase22_error", "message": str(e)})
        except:
            pass
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------- Manual test route ----------
@app.get("/test-connection")
def test_connection():
    """Check Render → Google WebApp connectivity"""
    import traceback
    try:
        if not WEBAPP_EXEC_URL:
            return "WEBAPP_EXEC_URL missing in environment", 500
        r = requests.post(WEBAPP_EXEC_URL, json={"action": "get_settings"}, timeout=25)
        return r.text, 200, {"Content-Type": "application/json"}
    except Exception as e:
        return traceback.format_exc(), 500

# ---------- Entry ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
