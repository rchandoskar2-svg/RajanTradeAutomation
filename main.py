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
ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")   # For live data

RESPONSE_TYPE = "code"
GRANT_TYPE = "authorization_code"


# ----------------------------------------------------
# ROOT
# ----------------------------------------------------
@app.get("/")
def home():
    return """
    RajanTradeAutomation LIVE ✔<br>
    <br>
    <a href='/fyers-auth'>Login to Fyers</a><br>
    <a href='/fyers-profile'>Check Fyers Profile</a><br>
    <a href='/fyers-quote?symbol=SBIN'>Test Live Quote</a><br>
    <a href='/debug-info'>Debug Info</a><br>
    """


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

    code = request.args.get("auth_code") or request.args.get("code")

    if not code:
        return jsonify({"error": "No auth code received"}), 400

    print("FYERS AUTH CODE:", code)

    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=REDIRECT_URI,
        response_type=RESPONSE_TYPE,
        grant_type=GRANT_TYPE
    )
    session.set_token(code)
    response = session.generate_token()
    print("TOKEN RESPONSE:", response)

    return jsonify(response)


# ----------------------------------------------------
# FYERS PROFILE
# ----------------------------------------------------
@app.get("/fyers-profile")
def fyers_profile():

    if not ACCESS_TOKEN:
        return {"ok": False, "error": "Access token missing in Render ENV"}, 400

    headers = {"Authorization": f"{CLIENT_ID}:{ACCESS_TOKEN}"}
    url = "https://api.fyers.in/api/v3/profile"

    r = requests.get(url, headers=headers)

    try:
        return r.json()
    except:
        return {"ok": False, "raw": r.text}


# ----------------------------------------------------
# FYERS QUOTE (LIVE PRICE)
# ----------------------------------------------------
@app.get("/fyers-quote")
def fyers_quote():

    symbol = request.args.get("symbol", "SBIN")

    if not ACCESS_TOKEN:
        return {"ok": False, "error": "Access token missing in Render ENV"}, 400

    url = "https://api.fyers.in/data-rest/v2/quotes/"
    headers = {"Authorization": f"{CLIENT_ID}:{ACCESS_TOKEN}"}

    payload = {"symbols": f"NSE:{symbol}-EQ"}

    r = requests.post(url, json=payload, headers=headers)

    try:
        return r.json()
    except:
        return {"ok": False, "raw": r.text}


# ----------------------------------------------------
# 🔥 DEBUG ENDPOINT (Chartink Payload Capture)
# ----------------------------------------------------
@app.post("/debug-chartink")
def debug_chartink():
    print("\n\n=======================")
    print("🔥 RAW CHARTINK ALERT 🔥")
    print("=======================\n")

    print("Headers:", dict(request.headers))
    print("Query Params:", request.args)
    print("Form Data:", request.form)
    print("JSON Body:", request.json)
    print("Raw Body:", request.data)

    return {"ok": True, "msg": "Captured Chartink data"}


# ----------------------------------------------------
# DEBUG INFO
# ----------------------------------------------------
@app.get("/debug-info")
def debug_info():
    return {
        "CLIENT_ID": CLIENT_ID,
        "REDIRECT_URI": REDIRECT_URI,
        "ACCESS_TOKEN_SET": True if ACCESS_TOKEN else False
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
