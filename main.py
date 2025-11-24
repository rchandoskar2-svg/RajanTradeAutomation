from flask import Flask, request, jsonify
import os
from fyers_apiv3 import fyersModel

app = Flask(__name__)

# -----------------------------
# ENV VARS FROM RENDER
# -----------------------------
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")          # N83MS34FQO-100
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")        # 9UUVU79KW8
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")    # https://rajantradeautomation.onrender.com/fyers-redirect

# -----------------------------
# ROOT
# -----------------------------
@app.get("/")
def root():
    return (
        "RajanTradeAutomation is LIVE.<br>"
        "Go to <b>/fyers-auth</b> to begin login.",
        200
    )

# -----------------------------
# STEP 1 — GET AUTH URL
# -----------------------------
@app.get("/fyers-auth")
def fyers_auth():
    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT_URI,
        response_type="code"
    )

    auth_url = session.generate_authcode()
    return jsonify({"ok": True, "auth_url": auth_url})

# -----------------------------
# STEP 2 — RECEIVE AUTH CODE
# -----------------------------
@app.get("/fyers-redirect")
def fyers_redirect():
    code = request.args.get("code")
    if not code:
        return "Missing ?code=xxxx", 400

    print("AUTH CODE RECEIVED:", code)

    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=REDIRECT_URI,
        response_type="code",
        grant_type="authorization_code"
    )

    session.set_token(code)
    response = session.generate_token()

    print("TOKEN RESPONSE:", response)
    return jsonify(response)

# -----------------------------
# HEALTH
# -----------------------------
@app.get("/health")
def health():
    return jsonify({"ok": True})

# -----------------------------
# RUN (Render)
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
