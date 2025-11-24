from flask import Flask, request, jsonify
from fyers_apiv3 import fyersModel
import os
import urllib.parse

app = Flask(__name__)

# ------------------------------------------------
# ENV FROM RENDER
# ------------------------------------------------
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")        # Example: N83MS34FQO-100
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")  # Example: https://rajantradeautomation.onrender.com/fyers-redirect

RESPONSE_TYPE = "code"
GRANT_TYPE = "authorization_code"


# ------------------------------------------------
# ROOT ROUTE
# ------------------------------------------------
@app.get("/")
def root():
    return "RajanTradeAutomation LIVE — use /fyers-auth", 200


# ------------------------------------------------
# STEP 1 — GENERATE AUTH URL
# ------------------------------------------------
@app.get("/fyers-auth")
def fyers_auth():

    encoded_redirect = urllib.parse.quote(REDIRECT_URI, safe='')

    # THIS IS THE CORRECT V3 URL
    auth_url = (
        f"https://api-t1.fyers.in/api/v3/generate-authcode?"
        f"client_id={CLIENT_ID}"
        f"&redirect_uri={encoded_redirect}"
        f"&response_type=code"
        f"&state=rajan_state"
    )

    return jsonify({"auth_url": auth_url})


# ------------------------------------------------
# STEP 2 — REDIRECT WITH ?code=XXXX
# ------------------------------------------------
@app.get("/fyers-redirect")
def fyers_redirect():

    auth_code = request.args.get("code")

    if not auth_code:
        return "Missing code", 400

    print("AUTH CODE RECEIVED:", auth_code)

    # -------- CREATE SESSION MODEL --------
    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=REDIRECT_URI,
        response_type=RESPONSE_TYPE,
        grant_type=GRANT_TYPE
    )

    # Set authorization code
    session.set_token(auth_code)

    # -------- REQUEST ACCESS TOKEN --------
    try:
        token_response = session.generate_token()
        print("TOKEN RESPONSE:", token_response)
        return jsonify(token_response)

    except Exception as e:
        print("ERROR:", e)
        return jsonify({"error": str(e)}), 500


# ------------------------------------------------
# HEALTH
# ------------------------------------------------
@app.get("/health")
def health():
    return jsonify({"ok": True})


# ------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
