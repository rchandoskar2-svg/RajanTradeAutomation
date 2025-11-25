from flask import Flask, request, jsonify
import os
import urllib.parse
import requests
from fyers_apiv3 import fyersModel

app = Flask(__name__)

# ----------------------------------------------------
# ENV VARIABLES
# ----------------------------------------------------
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")

RESPONSE_TYPE = "code"
GRANT_TYPE = "authorization_code"


# ----------------------------------------------------
# ROOT TEST
# ----------------------------------------------------
@app.get("/")
def home():
    return "RajanTradeAutomation LIVE ✔<br>Use /fyers-auth to login."


# ----------------------------------------------------
# STEP 1: Generate Auth URL
# ----------------------------------------------------
@app.get("/fyers-auth")
def fyers_auth():
    encoded_redirect = urllib.parse.quote(REDIRECT_URI, safe='')

    url = (
        f"https://api-t1.fyers.in/api/v3/generate-authcode?"
        f"client_id={CLIENT_ID}"
        f"&redirect_uri={encoded_redirect}"
        f"&response_type={RESPONSE_TYPE}"
        f"&state=rajan_state"
    )

    return jsonify({"auth_url": url})


# ----------------------------------------------------
# STEP 2: Handle Redirect (Auth Code → Access Token)
# ----------------------------------------------------
@app.get("/fyers-redirect")
def fyers_redirect():

    auth_code = request.args.get("auth_code")
    code = request.args.get("code")

    final_code = auth_code or code

    if not final_code:
        return jsonify({"error": "No auth code received"}), 400

    print("FYERS AUTH CODE:", final_code)

    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=REDIRECT_URI,
        response_type=RESPONSE_TYPE,
        grant_type=GRANT_TYPE
    )

    session.set_token(final_code)
    response = session.generate_token()

    print("TOKEN RESPONSE:", response)

    return jsonify(response)


# ----------------------------------------------------
# PROFILE API TEST (LIVE DATA CONFIRMATION)
# ----------------------------------------------------
@app.get("/fyers-profile")
def fyers_profile():

    ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

    if not ACCESS_TOKEN:
        return {"ok": False, "error": "Access token missing in Render ENV"}, 400

    headers = {"Authorization": f"{CLIENT_ID}:{ACCESS_TOKEN}"}

    url = "https://api.fyers.in/api/v3/profile"

    res = requests.get(url, headers=headers)

    # FYERS sometimes returns HTML on failure
    try:
        return res.json()
    except:
        return {
            "ok": False,
            "error": "Non-JSON response",
            "raw": res.text
        }


# ----------------------------------------------------
# HEALTH CHECK
# ----------------------------------------------------
@app.get("/health")
def health():
    return jsonify({"ok": True})


# ----------------------------------------------------
# RUN SERVER
# ----------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
