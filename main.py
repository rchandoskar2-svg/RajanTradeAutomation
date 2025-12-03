from flask import Flask, request, jsonify
import os
import requests
import json
import urllib.parse
from fyers_apiv3 import fyersModel   # हे आधीच होतं, तसेच ठेवा

app = Flask(__name__)

# ----------------------------------------------------
# ENV VARIABLES
# ----------------------------------------------------
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")
ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

# Your Google Apps Script EXEC URL
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()

# Chartink secret token (same as in webhook URL)
CHARTINK_TOKEN = os.getenv("CHARTINK_TOKEN", "").strip()

RESPONSE_TYPE = "code"
GRANT_TYPE = "authorization_code"


# ----------------------------------------------------
# ROOT
# ----------------------------------------------------
@app.get("/")
def home():
    return (
        "RajanTradeAutomation ACTIVE ✔<br>"
        "Routes: /fyers-auth /fyers-profile /chartink-alert /health"
    )


# ----------------------------------------------------
# ----------- FYERS AUTH FLOW ------------------------
# ----------------------------------------------------
@app.get("/fyers-auth")
def fyers_auth():
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
    auth_code = request.args.get("auth_code") or request.args.get("code")
    if not auth_code:
        return {"error": "No auth code"}, 400

    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=REDIRECT_URI,
        response_type=RESPONSE_TYPE,
        grant_type=GRANT_TYPE,
    )

    session.set_token(auth_code)
    response = session.generate_token()
    return jsonify(response)


@app.get("/fyers-profile")
def fyers_profile():
    """
    current ACCESS_TOKEN वापरून Fyers profile API test.
    """
    if not ACCESS_TOKEN or not CLIENT_ID:
        return jsonify({"ok": False, "error": "Access Token or Client ID Missing"}), 400

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
# ----------- CHARTINK DEBUG ROUTE -------------------
# ----------------------------------------------------
@app.post("/debug-chartink")
def debug_chartink():
    print("

========== RAW CHARTINK ALERT (DEBUG) ==========")
    print("Headers:", dict(request.headers))
    print("Body:", request.data.decode(errors="ignore"))
    print("===============================================
")
    return {"ok": True, "msg": "debug logged"}, 200


# ----------------------------------------------------
# ----------- MAIN CHARTINK ALERT ROUTE --------------
# ----------------------------------------------------
@app.route("/chartink-alert", methods=["GET", "POST"])
def chartink_alert():
    """
    Chartink webhook endpoint.
    """
    print("

====== CHARTINK ALERT HIT ======")
    print("Method:", request.method)
    print("Query args:", dict(request.args))

    # ---- Token validation (query param) ----
    incoming_token = request.args.get("token", "").strip()
    if CHARTINK_TOKEN and incoming_token != CHARTINK_TOKEN:
        print("❌ Invalid token:", incoming_token)
        return {"ok": False, "error": "Invalid token"}, 403

    # ---- Handle GET pings gracefully ----
    if request.method == "GET":
        print("GET ping received on /chartink-alert → returning pong")
        print("============================================
")
        return {"ok": True, "msg": "pong"}, 200

    # ---- POST: actual alert from Chartink ----
    try:
        body_raw = request.data.decode(errors="ignore")
        print("RAW BODY:", body_raw or "[EMPTY]")

        # Try JSON first
        data = json.loads(body_raw) if body_raw else {}

    except Exception as e:
        print("❌ JSON parse error:", str(e))
        return {"ok": False, "error": "Invalid JSON"}, 400

    # Safety: must contain at least "stocks" key
    if not isinstance(data, dict) or "stocks" not in data:
        print("❌ Invalid payload structure, 'stocks' missing")
        print("============================================
")
        return {"ok": False, "error": "Invalid payload (no stocks)"}, 400

    # ---- Forward directly to Google Apps Script WebApp ----
    if not WEBAPP_URL:
        print("❌ WEBAPP_URL not configured in environment")
        return {"ok": False, "error": "WEBAPP_URL not set"}, 500

    try:
        # DIRECT forward – NO extra wrapper, NO action/payload
        res = requests.post(
            WEBAPP_URL,
            json=data,
            timeout=10,
        )
        print("Forward Response status:", res.status_code)
        print("Forward Response body:", res.text)

    except Exception as e:
        print("❌ FORWARD ERROR:", str(e))
        print("============================================
")
        return {"ok": False, "error": "Forward failed"}, 500

    print("====== CHARTINK ALERT PROCESSED SUCCESSFULLY ======
")
    return {"ok": True}, 200


# ----------------------------------------------------
# HEALTH CHECK
# ----------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True}


# ----------------------------------------------------
# RUN SERVER  (ping / keep-alive भाग - नको काढू)
# ----------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
