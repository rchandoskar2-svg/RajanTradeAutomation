from flask import Flask, request, jsonify
import requests
import os
import urllib.parse

app = Flask(__name__)

CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")

@app.get("/")
def root():
    return (
        "RajanTradeAutomation is LIVE.<br>"
        "Use <b>/fyers-auth</b> to start Fyers Login Flow.",
        200
    )

@app.get("/fyers-auth")
def fyers_auth():
    try:
        encoded_redirect = urllib.parse.quote(REDIRECT_URI, safe='')
        auth_url = (
            f"https://api-t1.fyers.in/api/v3/generate-authcode?"
            f"client_id={CLIENT_ID}"
            f"&redirect_uri={encoded_redirect}"
            f"&response_type=code"
            f"&state=rajan_state"
        )
        return jsonify({"ok": True, "auth_url": auth_url})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.get("/fyers-redirect")
def fyers_redirect():

    code = request.args.get("code")

    if not code:
        return "Missing code. Login failed.", 400

    print("=====================================")
    print("AUTH CODE:", code)
    print("=====================================")

    token_request = {
        "grant_type": "authorization_code",
        "appId": CLIENT_ID,
        "code": code,
        "secret_key": SECRET_KEY
    }

    try:
        # IMPORTANT FIX → Use api-t1 domain
        res = requests.post("https://api-t1.fyers.in/api/v3/token", json=token_request)
        text = res.text

        print("RAW TOKEN RESPONSE:", text)

        try:
            return jsonify(res.json())
        except:
            return f"Token endpoint returned non-JSON response (status={res.status_code}):\n\n{text}"

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.get("/health")
def health():
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
