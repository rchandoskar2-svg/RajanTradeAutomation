# =====================================================
# RajanTradeAutomation – FYERS AUTH + ENGINE BASE
# =====================================================

import os
import time
import threading
import requests
from datetime import datetime, timedelta
from flask import Flask, request
from fyers_apiv3 import fyersModel
from fyers_apiv3.FyersWebsocket import data_ws

# ---------------- ENV ----------------
FYERS_CLIENT_ID = os.environ.get("FYERS_CLIENT_ID")
FYERS_SECRET_ID = os.environ.get("FYERS_SECRET_ID")
FYERS_REDIRECT_URI = os.environ.get("FYERS_REDIRECT_URI")
FYERS_ACCESS_TOKEN = os.environ.get("FYERS_ACCESS_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL")
PORT = int(os.environ.get("PORT", 10000))

# ---------------- FLASK ----------------
app = Flask(__name__)

@app.route("/")
def home():
    return "RajanTradeAutomation Alive"

# =====================================================
# FYERS LOGIN → AUTH CODE → ACCESS TOKEN
# =====================================================

@app.route("/fyers-login")
def fyers_login():
    session = fyersModel.SessionModel(
        client_id=FYERS_CLIENT_ID,
        secret_key=FYERS_SECRET_ID,
        redirect_uri=FYERS_REDIRECT_URI,
        response_type="code",
        grant_type="authorization_code"
    )
    url = session.generate_authcode()
    return f'<a href="{url}">Click here to login to FYERS</a>'

@app.route("/fyers-redirect")
def fyers_redirect():
    auth_code = request.args.get("auth_code")
    if not auth_code:
        return "Auth code missing"

    session = fyersModel.SessionModel(
        client_id=FYERS_CLIENT_ID,
        secret_key=FYERS_SECRET_ID,
        redirect_uri=FYERS_REDIRECT_URI,
        response_type="code",
        grant_type="authorization_code"
    )

    session.set_token(auth_code)
    token_response = session.generate_token()

    access_token = token_response.get("access_token")

    if not access_token:
        return f"Token error: {token_response}"

    return (
        "<h3>ACCESS TOKEN GENERATED SUCCESSFULLY</h3>"
        "<p>Copy this token and put it in Render ENV:</p>"
        f"<textarea rows='5' cols='100'>{access_token}</textarea>"
    )

# ---------------- MAIN ----------------
if __name__ == "__main__":
    print("Starting Flask on port", PORT)
    app.run(host="0.0.0.0", port=PORT)
