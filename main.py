from flask import Flask, request, jsonify
import os
import urllib.parse
from fyers_apiv3 import fyersModel

app = Flask(__name__)

# ---------------------------------------------
# ENVIRONMENT VARIABLES
# ---------------------------------------------
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")          # N83MS34FQO-100
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")        # 9UUVU79KW8
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")    # https://rajantradeautomation.onrender.com/fyers-redirect

RESPONSE_TYPE = "code"
GRANT_TYPE = "authorization_code"


# ---------------------------------------------
# ROOT
# ---------------------------------------------
@app.get("/")
def home():
    return "RajanTradeAutomation LIVE<br>Use /fyers-auth to start.", 200


# ---------------------------------------------
# STEP 1 → GENERATE AUTHCODE URL
# ---------------------------------------------
@app.get("/fyers-auth")
def make_auth_url():

    encoded_redirect = urllib.parse.quote(REDIRECT_URI, safe='')

    auth_url = (
        f"https://api-t1.fyers.in/api/v3/generate-authcode?"
        f"client_id={CLIENT_ID}"
        f"&redirect_uri={encoded_redirect}"
        f"&response_type={RESPONSE_TYPE}"
        f"&state=rajan_state"
    )

    return jsonify({"auth_url": auth_url})


# ---------------------------------------------
# STEP 2 → FYERS RETURNS ?auth_code=XXXX
# ---------------------------------------------
@app.get("/fyers-redirect")
def fyers_redirect():

    auth_code = request.args.get("auth_code")
    code = request.args.get("code")

    # Fyers sometimes returns auth_code, sometimes code
    final_code = auth_code or code

    if not final_code:
        return jsonify({"error": "No auth_code received"}), 400

    print("==========================")
    print("AUTH CODE RECEIVED:", final_code)
    print("==========================")

    # -----------------------------------------
    # Use FYERS SDK for token exchange
    # -----------------------------------------
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


# ---------------------------------------------
# HEALTH
# ---------------------------------------------
@app.get("/health")
def health():
    return jsonify({"ok": True})


# ---------------------------------------------
# RUN SERVER
# ---------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
