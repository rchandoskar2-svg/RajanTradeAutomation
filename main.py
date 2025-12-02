"""
RajanTradeAutomation - Kushal Strategy Server (v1.1)
Flask server on Render:
- /health         : UptimeRobot ping (keeps free tier awake)
- /fyers-auth     : Generate Fyers auth URL (manual use)
- /fyers-redirect : Exchange auth_code -> access/refresh token (manual)
- /fyers-profile  : Quick test using current ACCESS_TOKEN
- /run_strategy   : Placeholder for main Kushal Sector FnO logic
"""

import os
import json
import urllib.parse

from flask import Flask, request, jsonify
import requests
from fyers_apiv3 import fyersModel

app = Flask(__name__)

# ----------------------------------------------------
# ENV VARIABLES (exact keys as in Render)
# ----------------------------------------------------
CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
SECRET_KEY = os.getenv("FYERS_SECRET_KEY", "").strip()
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI", "").strip()
ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
REFRESH_TOKEN = os.getenv("FYERS_REFRESH_TOKEN", "").strip()

WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()   # Google Apps Script exec URL
MODE = os.getenv("MODE", "SIM").strip()            # SIM / LIVE (future use)

# तुझ्या Render env मधील INTERVAL_SECS default 1800 आहे (30 मिनिटे)
try:
    INTERVAL_SECS = int(os.getenv("INTERVAL_SECS", "1800").strip() or "1800")
except Exception:
    INTERVAL_SECS = 1800

RESPONSE_TYPE = "code"
GRANT_TYPE = "authorization_code"


# ----------------------------------------------------
# ROOT + HEALTH (UptimeRobot)
# ----------------------------------------------------
@app.get("/")
def home():
    return (
        "RajanTradeAutomation ACTIVE ✔<br>"
        "Routes: /health /fyers-auth /fyers-profile /run_strategy"
    )


@app.get("/health")
def health():
    """
    Simple health check for UptimeRobot.
    Just returns ok so that Render free tier stays awake.
    """
    return {
        "ok": True,
        "mode": MODE,
        "interval_secs": INTERVAL_SECS
    }, 200


# ----------------------------------------------------
# ----------- FYERS AUTH / TOKEN ROUTES --------------
# (used rarely, mainly when token expires)
# ----------------------------------------------------
@app.get("/fyers-auth")
def fyers_auth():
    """
    Generate auth URL (manual use in browser).
    """
    if not CLIENT_ID or not REDIRECT_URI:
        return jsonify({"error": "Missing CLIENT_ID or REDIRECT_URI"}), 500

    encoded_redirect = urllib.parse.quote(REDIRECT_URI, safe="")
    url = (
        "https://api-t1.fyers.in/api/v3/generate-authcode?"
        f"client_id={CLIENT_ID}"
        f"&redirect_uri={encoded_redirect}"
        f"&response_type={RESPONSE_TYPE}"
        f"&state=rajan_state"
    )
    return jsonify({"auth_url": url})


@app.get("/fyers-redirect")
def fyers_redirect():
    """
    Redirect URI endpoint.
    Fyers will call this once you approve the app.
    It exchanges auth_code for access_token + refresh_token.
    (Mostly for manual use / debugging)
    """
    auth_code = request.args.get("auth_code") or request.args.get("code")
    if not auth_code:
        return {"error": "No auth code"}, 400

    if not (CLIENT_ID and SECRET_KEY and REDIRECT_URI):
        return {"error": "Missing CLIENT_ID / SECRET_KEY / REDIRECT_URI"}, 500

    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=REDIRECT_URI,
        response_type=RESPONSE_TYPE,
        grant_type=GRANT_TYPE,
    )

    session.set_token(auth_code)
    response = session.generate_token()

    # NOTE: Response मध्ये access_token / refresh_token येतो.
    # हे Render env मध्ये manually अपडेट करावे लागतील.
    # पुढे auto-refresh हवं असेल तर वेगळा route बनवू.
    return jsonify(response)


@app.get("/fyers-profile")
def fyers_profile():
    """
    Quick test: current ACCESS_TOKEN वापरून profile call.
    Token expire झाला असेल तर error येईल.
    """
    if not ACCESS_TOKEN or not CLIENT_ID:
        return {"ok": False, "error": "Access Token or Client ID Missing"}, 400

    headers = {"Authorization": f"{CLIENT_ID}:{ACCESS_TOKEN}"}
    url = "https://api.fyers.in/api/v3/profile"

    try:
        res = requests.get(url, headers=headers, timeout=10)
        try:
            data = res.json()
        except Exception:
            data = {"raw": res.text}
        return jsonify({"status_code": res.status_code, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ----------------------------------------------------
# ----------- MAIN STRATEGY ROUTE (Placeholder) ------
# ----------------------------------------------------
@app.post("/run_strategy")
def run_strategy():
    """
    इथे पुढे Kushal Varshney Sector FnO Strategy logic येईल:
    - Nifty 50 adv/decl + sector performance (via Fyers)
    - FnO stock list filter (<= 2.5% move)
    - 5-min candles (WebSocket/REST) + lowest volume candle logic
    - Signals Sheets/WebApp कडे पाठवणे (WEBAPP_URL ला POST करून)

    सध्या हा फक्त dummy response देतो.
    """
    payload = {}
    try:
        if request.data:
            payload = json.loads(request.data.decode("utf-8"))
    except Exception:
        payload = {}

    return jsonify({
        "ok": True,
        "msg": "Strategy placeholder running",
        "mode": MODE,
        "interval_secs": INTERVAL_SECS,
        "request_payload": payload
    }), 200


# ----------------------------------------------------
# RUN SERVER (local testing)
# ----------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
