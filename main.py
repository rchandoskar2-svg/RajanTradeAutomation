# ===========================================================
# RajanTradeAutomation – Phase 2 (Stable + Stage pass-through)
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
    # काही WebApp actions plain text देतील; json नसलं तरी OK
    try:
        return r.json()
    except Exception:
        return {"ok": True, "raw": r.text}

# ---------- Health Check ----------
@app.get("/health")
def health():
    return jsonify({"ok": True, "app": APP_NAME, "ts": int(time.time())})

# ---------- Chartink Webhook ----------
@app.post("/chartink-alert")
def chartink_alert():
    """
    Accepts Chartink webhook.
    Stage (1/2) is read in this priority:
      1) URL query ?stage=1|2
      2) JSON keys: alert_stage / stage / ALERT_STAGE
      3) HTTP header: X-Alert-Stage
    Then forwarded to Google WebApp as payload.alert_stage so that
    Alert#1 clears A3:A and Alert#2 appends.
    """
    try:
        # --- token guard (optional) ---
        token = request.args.get("token")
        if CHARTINK_TOKEN and token and token != CHARTINK_TOKEN:
            return jsonify({"ok": False, "error": "Invalid token"}), 403

        data = request.get_json(force=True, silent=True) or {}

        # --- stage normalization ---
        stage = (
            request.args.get("stage")
            or str(data.get("alert_stage") or data.get("stage") or data.get("ALERT_STAGE") or "")
            or request.headers.get("X-Alert-Stage")
        )
        try:
            stage_int = int(stage)
            if stage_int not in (1, 2):
                stage_int = None
        except Exception:
            stage_int = None

        # Ensure payload dict exists, inject alert_stage if available
        payload = dict(data) if isinstance(data, dict) else {"raw": data}
        if stage_int is not None:
            payload["alert_stage"] = stage_int

        # Forward to Google WebApp (Phase-2 style)
        res = gs_post({"action": "chartink_import", "payload": payload})
        return jsonify({"ok": True, "sheet": res, "forwarded_stage": stage_int})

    except Exception as e:
        # best-effort error log to WebApp
        try:
            gs_post({"action": "phase22_error", "message": str(e)})
        except Exception:
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
    except Exception:
        return traceback.format_exc(), 500

# ---------- Entry ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
