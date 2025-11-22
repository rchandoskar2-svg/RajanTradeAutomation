from flask import Flask, request, jsonify
import requests
import os
import urllib.parse

app = Flask(__name__)

# ------------------------------------------------
# ENVIRONMENT VARIABLES (Render Settings)
# ------------------------------------------------
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")          # Example: N83MS34FQO-100
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")        # Example: 9UUVU79KWB
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")    # Example: https://rajantradeautomation.onrender.com/fyers-redirect


# ------------------------------------------------
# ROOT ROUTE
# ------------------------------------------------
@app.get("/")
def root():
    return (
        "RajanTradeAutomation is LIVE.<br>"
        "Use <b>/fyers-auth</b> to start Fyers Login Flow.",
        200
    )


# ------------------------------------------------
# STEP 1 — GENERATE FYERS AUTH URL
# ------------------------------------------------
@app.get("/fyers-auth")
def fyers_auth():

    if not CLIENT_ID or not REDIRECT_URI:
        return jsonify({
            "ok": False,
            "error": "CLIENT_ID or REDIRECT_URI missing"
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
# STEP 2 — RECEIVE AUTH CODE & EXCHANGE TOKEN
# ------------------------------------------------
@app.get("/fyers-redirect")
def fyers_redirect():

    # Sometimes Fyers sends ?auth_code, sometimes ?code
    code = request.args.get("auth_code") or request.args.get("code")

    if not code:
        return (
            "Fyers did not return ?code or ?auth_code<br>"
            "Login NOT completed.",
            400
        )

    print("=====================================")
    print("AUTH CODE Received:", code)
    print("=====================================")

    # Token request payload
    token_request = {
        "grant_type": "authorization_code",
        "appId": CLIENT_ID,
        "code": code,
        "secret_key": SECRET_KEY
    }

    try:
        res = requests.post("https://api.fyers.in/api/v3/token", json=token_request)
        text = res.text
        
        print("RAW TOKEN RESPONSE:", text)

        # Try to parse JSON, fallback if HTML
        try:
            token_data = res.json()
        except:
            return (
                f"Token endpoint returned non-JSON response (status={res.status_code})<br><br>"
                f"{text}",
                503
            )

        return jsonify(token_data)

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ------------------------------------------------
# HEALTH CHECK
# ------------------------------------------------
@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "RajanTradeAutomation"})


# ------------------------------------------------
# START SERVER
# ------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
