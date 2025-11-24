from flask import Flask, request, jsonify
import requests
import os
import urllib.parse

app = Flask(__name__)

# ------------------------------------------------
# ENV VARS
# ------------------------------------------------
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")          # N83MS34FQO-100
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")        # 9UUVU79KW8
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")    # https://rajantradeautomation.onrender.com/fyers-redirect


# ------------------------------------------------
# ROOT
# ------------------------------------------------
@app.get("/")
def root():
    return "RajanTradeAutomation is LIVE.<br>Visit /fyers-auth", 200


# ------------------------------------------------
# STEP 1 — GENERATE AUTHCODE URL
# ------------------------------------------------
@app.get("/fyers-auth")
def fyers_auth():

    encoded_redirect = urllib.parse.quote(REDIRECT_URI, safe='')

    # IMPORTANT: Using api-t1 — this is required
    auth_url = (
        f"https://api-t1.fyers.in/api/v3/generate-authcode?"
        f"client_id={CLIENT_ID}"
        f"&redirect_uri={encoded_redirect}"
        f"&response_type=code"
        f"&state=rajan_state"
    )

    return jsonify({"auth_url": auth_url})


# ------------------------------------------------
# STEP 2 — REDIRECT HANDLING
# ------------------------------------------------
@app.get("/fyers-redirect")
def fyers_redirect():

    auth_code = request.args.get("auth_code") or request.args.get("code")

    if not auth_code:
        return "Error: auth_code missing", 400

    print("\n============================")
    print("AUTH CODE RECEIVED:", auth_code)
    print("============================\n")

    token_payload = {
        "grant_type": "authorization_code",
        "appId": CLIENT_ID,
        "code": auth_code,
        "secret_key": SECRET_KEY,
        "redirect_uri": REDIRECT_URI
    }

    print("\nSending token request...\n")

    r = requests.post(
        "https://api-t1.fyers.in/api/v3/token",
        json=token_payload
    )

    try:
        token_data = r.json()
    except:
        return "FYERS returned non-JSON response:\n" + r.text, 503

    print("\nTOKEN RESPONSE:")
    print(token_data)
    print("\n")

    return jsonify(token_data)


# ------------------------------------------------
# HEALTH CHECK
# ------------------------------------------------
@app.get("/health")
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
