from flask import Flask, request, jsonify
import requests
import os
import urllib.parse

app = Flask(__name__)

# ------------------------------------------------
# ENVIRONMENT VARIABLES (Render Settings)
# ------------------------------------------------
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")

# ------------------------------------------------
# ROOT ROUTE — THIS MUST WORK IN BROWSER
# ------------------------------------------------
@app.get("/")
def root():
    return (
        "RajanTradeAutomation is LIVE.<br>"
        "Use <b>/fyers-auth</b> to start Fyers Login Flow.",
        200
    )

# ------------------------------------------------
# FYERS AUTH — GENERATE AUTHCODE URL
# ------------------------------------------------
@app.get("/fyers-auth")
def fyers_auth():

    if not CLIENT_ID or not REDIRECT_URI:
        return jsonify({
            "ok": False,
            "error": "Environment variables missing"
        }), 500

    encoded_redirect = urllib.parse.quote(REDIRECT_URI, safe='')

    auth_url = (
        f"https://api-t1.fyers.in/api/v3/generate-authcode?"
        f"client_id={CLIENT_ID}"
        f"&redirect_uri={encoded_redirect}"
        f"&response_type=code"
        f"&state=rajan_state"
    )

    return jsonify({"ok": True, "auth_url": auth_url})


# ------------------------------------------------
# FYERS REDIRECT — FYERS RETURNS ?code=XXXX HERE
# ------------------------------------------------
@app.get("/fyers-redirect")
def fyers_redirect():

    code = request.args.get("code")

    if not code:
        return (
            "Missing code. Fyers did not return ?code=xxxx<br>"
            "Login was NOT completed.",
            400
        )

    print("=====================================")
    print("Received AUTH CODE from FYERS:", code)
    print("=====================================")

    # ------------------------------------------------
    # STEP 2 — Exchange code → access token
    #
    # (We will enable this AFTER root route works and
    #  redirect works. No need to activate now)
    # ------------------------------------------------
    #
    # token_request = {
    #     "grant_type": "authorization_code",
    #     "appId": CLIENT_ID,
    #     "code": code,
    #     "secret_key": SECRET_KEY
    # }
    #
    # res = requests.post("https://api.fyers.in/api/v3/token", json=token_request)
    # token_data = res.json()
    #
    # return jsonify(token_data)

    return (
        f"Auth CODE received successfully: {code}<br>"
        f"Token exchange ready.",
        200
    )


# ------------------------------------------------
# HEALTH CHECK — FOR RENDER
# ------------------------------------------------
@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "RajanTradeAutomation"})


# ------------------------------------------------
# START SERVER
# ------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
