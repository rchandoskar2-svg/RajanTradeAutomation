from flask import Flask, request, jsonify
import os
import requests
import json
import urllib.parse
from fyers_apiv3 import fyersModel

app = Flask(__name__)

# ----------------------------------------------------
# ENV VARIABLES
# ----------------------------------------------------
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")
ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

WEBAPP_URL = os.getenv("WEBAPP_URL")   # <<< Your Google Script Exec URL
CHARTINK_TOKEN = os.getenv("CHARTINK_TOKEN", "")

RESPONSE_TYPE = "code"
GRANT_TYPE = "authorization_code"


# ----------------------------------------------------
# ROOT
# ----------------------------------------------------
@app.get("/")
def home():
    return "RajanTradeAutomation ACTIVE ✔ <br> Routes: /fyers-auth /fyers-profile /chartink-alert"


# ----------------------------------------------------
# ----------- FYERS AUTH FLOW ------------------------
# ----------------------------------------------------
@app.get("/fyers-auth")
def fyers_auth():
    encoded_redirect = urllib.parse.quote(REDIRECT_URI, safe='')
    url = (
        f"https://api-t1.fyers.in/api/v3/generate-authcode?"
        f"client_id={CLIENT_ID}&redirect_uri={encoded_redirect}"
        f"&response_type={RESPONSE_TYPE}&state=rajan_state"
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
        grant_type=GRANT_TYPE
    )

    session.set_token(auth_code)
    response = session.generate_token()
    return jsonify(response)


@app.get("/fyers-profile")
def fyers_profile():

    if not ACCESS_TOKEN:
        return {"ok": False, "error": "Access Token Missing"}, 400

    headers = {"Authorization": f"{CLIENT_ID}:{ACCESS_TOKEN}"}
    url = "https://api.fyers.in/api/v3/profile"

    res = requests.get(url, headers=headers)
    try:
        return res.json()
    except:
        return {"ok": False, "error": "Non-JSON", "raw": res.text}


# ----------------------------------------------------
# ----------- CHARTINK DEBUG ROUTE -------------------
# ----------------------------------------------------
@app.post("/debug-chartink")
def debug_chartink():

    print("\n\n========== RAW CHARTINK ALERT ==========")
    print("Headers:", dict(request.headers))
    print("Body:", request.data.decode())
    print("========================================\n")

    return {"ok": True, "msg": "debug logged"}, 200


# ----------------------------------------------------
# ----------- MAIN CHARTINK ALERT ROUTE --------------
# ----------------------------------------------------
@app.post("/chartink-alert")
def chartink_alert():

    print("\n\n====== CHARTINK ALERT RECEIVED ======")

    try:
        body_raw = request.data.decode()
        print("RAW BODY:", body_raw)

        data = json.loads(body_raw)
    except:
        return {"ok": False, "error": "Invalid JSON"}, 400

    incoming_token = request.args.get("token", "")

    # Validate token (if set)
    if CHARTINK_TOKEN and incoming_token != CHARTINK_TOKEN:
        print("❌ Invalid token")
        return {"ok": False, "error": "Invalid token"}, 403

    # Forward to Google Apps Script WebApp
    try:
        forward_data = {
            "action": "chartink_import",
            "payload": data
        }

        res = requests.post(
            WEBAPP_URL,
            json=forward_data,
            timeout=10
        )

        print("Forward Response:", res.text)

    except Exception as e:
        print("FORWARD ERROR:", str(e))
        return {"ok": False, "error": "Forward failed"}, 500

    print("====== CHARTINK ALERT PROCESSED ======\n")
    return {"ok": True}, 200


# ----------------------------------------------------
# HEALTH CHECK
# ----------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True}


# ----------------------------------------------------
# RUN SERVER
# ----------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
