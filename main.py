from flask import Flask, request, jsonify
import os
import requests
import json
import urllib.parse
from fyers_apiv3 import fyersModel

app = Flask(__name__)

# ----------------------------------------------------
# ENV VARIABLES
# ----------------------------------------------------
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")
ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

WEBAPP_URL = os.getenv("WEBAPP_URL", "")
CHARTINK_TOKEN = os.getenv("CHARTINK_TOKEN", "")

RESPONSE_TYPE = "code"
GRANT_TYPE = "authorization_code"


# ----------------------------------------------------
# ROOT (Home + Ping + Info)
# ----------------------------------------------------
@app.get("/")
def home():
    return (
        "RajanTradeAutomation ✔ Web Server Running<br>"
        "Routes: /fyers-auth /fyers-redirect /fyers-profile /get-quotes /chartink-alert /health"
    )


# ----------------------------------------------------
# FYERS AUTH FLOW
# ----------------------------------------------------
@app.get("/fyers-auth")
def fyers_auth():
    if not CLIENT_ID or not REDIRECT_URI:
        return jsonify({"error": "CLIENT_ID or REDIRECT_URI missing"}), 500

    encoded_redirect = urllib.parse.quote(REDIRECT_URI, safe="")
    url = (
        "https://api-t1.fyers.in/api/v3/generate-authcode?"
        f"client_id={CLIENT_ID}"
        f"&redirect_uri={encoded_redirect}"
        f"&response_type=code&state=rajan_state"
    )
    return jsonify({"auth_url": url})


@app.get("/fyers-redirect")
def fyers_redirect():
    auth_code = request.args.get("auth_code") or request.args.get("code")
    if not auth_code:
        return {"error": "No auth code"}, 400

    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=REDIRECT_URI,
        response_type="code",
        grant_type="authorization_code",
    )

    session.set_token(auth_code)
    response = session.generate_token()   # याच्यातून ACCESS_TOKEN मिळतो
    return jsonify(response)


# ----------------------------------------------------
# FYERS PROFILE CHECK
# ----------------------------------------------------
@app.get("/fyers-profile")
def fyers_profile():
    if not ACCESS_TOKEN or not CLIENT_ID:
        return {"ok": False, "error": "Token or ClientID missing"}, 400

    headers = {"Authorization": f"{CLIENT_ID}:{ACCESS_TOKEN}"}
    url = "https://api.fyers.in/api/v3/profile"

    try:
        res = requests.get(url, headers=headers, timeout=10)
        return {
            "status_code": res.status_code,
            "data": res.json() if "json" in dir(res) else res.text,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


# ----------------------------------------------------
# GET QUOTES (तुझ्या Sample code वर आधारित)
# ----------------------------------------------------
@app.get("/get-quotes")
def get_quotes():
    """
    Example:
    /get-quotes?symbols=NSE:SBIN-EQ,NSE:RELIANCE-EQ
    """
    if not ACCESS_TOKEN:
        return {"ok": False, "error": "ACCESS TOKEN missing"}, 400

    symbols = request.args.get("symbols", "")
    if not symbols:
        return {"ok": False, "error": "Symbols missing"}, 400

    fy = fyersModel.FyersModel(client_id=CLIENT_ID, token=ACCESS_TOKEN, is_async=False)
    data = {"symbols": symbols}

    try:
        response = fy.quotes(data=data)
        return jsonify(response)
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


# ----------------------------------------------------
# OLD CHARTINK → GOOGLE SCRIPT
# ----------------------------------------------------
@app.route("/chartink-alert", methods=["GET", "POST"])
def chartink_alert():
    if request.method == "GET":
        return {"ok": True, "msg": "pong"}

    try:
        data = json.loads(request.data.decode("utf-8"))
    except:
        return {"ok": False, "error": "invalid json"}, 400

    if not WEBAPP_URL:
        return {"ok": False, "error": "WEBAPP_URL missing"}, 500

    try:
        res = requests.post(WEBAPP_URL, json=data)
        return {"ok": True, "forward_status": res.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


# ----------------------------------------------------
# HEALTH (UptimeRobot 24×7)
# ----------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True}


# ----------------------------------------------------
# SERVER START
# ----------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
