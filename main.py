from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# ---------------------------------------
# ENV VARIABLES FROM RENDER
# ---------------------------------------
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")          # Example: N83MS34FQO-100
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")    # MUST be exact, no encoding


# ---------------------------------------
# ROOT
# ---------------------------------------
@app.get("/")
def index():
    return "RajanTradeAutomation — LIVE", 200


# ---------------------------------------
# STEP 1 — GENERATE AUTHCODE URL
# ---------------------------------------
@app.get("/fyers-auth")
def fyers_auth():

    if not CLIENT_ID or not SECRET_KEY or not REDIRECT_URI:
        return jsonify({"ok": False, "error": "Missing env vars"}), 500

    # DO NOT url-encode redirect_uri (Fyers internally handles this)
    auth_url = (
        "https://api.fyers.in/api/v3/generate-authcode"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        "&response_type=code"
        "&state=rajan_state"
    )

    return jsonify({"ok": True, "auth_url": auth_url})


# ---------------------------------------
# STEP 2 — RECEIVE AUTH CODE + EXCHANGE FOR TOKEN
# ---------------------------------------
@app.get("/fyers-redirect")
def fyers_redirect():

    code = request.args.get("code")

    if not code:
        return jsonify({"ok": False, "error": "Missing ?code=xxxx from Fyers"}), 400

    print("AUTH CODE:", code)

    token_req = {
        "grant_type": "authorization_code",
        "appId": CLIENT_ID,
        "code": code,
        "secret_key": SECRET_KEY
    }

    try:
        r = requests.post("https://api.fyers.in/api/v3/token", json=token_req)
        txt = r.text

        print("RAW TOKEN RESPONSE:", txt)

        # If HTML returned => convert error
        if txt.startswith("<"):
            return jsonify({"ok": False, "error": "Fyers returned HTML (503/500)", "html": txt}), 503

        return jsonify(r.json())

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ---------------------------------------
# HEALTH
# ---------------------------------------
@app.get("/health")
def health():
    return jsonify({"ok": True})


# ---------------------------------------
# SERVER
# ---------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
