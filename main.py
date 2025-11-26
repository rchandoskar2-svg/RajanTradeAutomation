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

RESPONSE_TYPE = "code"
GRANT_TYPE = "authorization_code"

# 🔹 Fyers data base (LIVE data इथून येईल)
FYERS_DATA_BASE = "https://api-t1.fyers.in/data"


# ----------------------------------------------------
# ROOT TEST
# ----------------------------------------------------
@app.get("/")
def home():
    return "RajanTradeAutomation LIVE ✔<br>Use /fyers-auth to login."


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

    auth_code = request.args.get("auth_code")
    code = request.args.get("code")

    final_code = auth_code or code

    if not final_code:
        return jsonify({"error": "No auth code received"}), 400

    print("FYERS AUTH CODE:", final_code)

    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=REDIRECT_URI,
        response_type=RESPONSE_TYPE,
        grant_type=GRANT_TYPE
    )

    session.set_token(final_code)
    response = session.generate_token()

    print("TOKEN RESPONSE:", response)

    return jsonify(response)


# ----------------------------------------------------
# HELPER: auth header for data APIs
# ----------------------------------------------------
def get_auth_header():
    access_token = os.getenv("FYERS_ACCESS_TOKEN")
    if not (CLIENT_ID and access_token):
        return None
    return {"Authorization": f"{CLIENT_ID}:{access_token}"}


# ----------------------------------------------------
# PROFILE API TEST (LIVE DATA CONFIRMATION)
# ----------------------------------------------------
@app.get("/fyers-profile")
def fyers_profile():

    headers = get_auth_header()
    if not headers:
        return {"ok": False, "error": "Access token or client id missing in Render ENV"}, 400

    # ✅ Correct api-t1 profile URL
    url = "https://api-t1.fyers.in/api/v3/profile"

    res = requests.get(url, headers=headers)

    # FYERS sometimes returns HTML on failure
    try:
        return res.json()
    except Exception:
        return {
            "ok": False,
            "error": "Non-JSON response",
            "raw": res.text
        }


# ----------------------------------------------------
# FYERS QUOTE (LIVE LTP + VOLUME + %CHG)
# ----------------------------------------------------
@app.post("/fyers-quote")
def fyers_quote():
    """
    Expected JSON:
    {
      "symbols": ["NSE:SBIN-EQ", "NSE:RELIANCE-EQ"]
    }
    """
    body = request.get_json(silent=True) or {}
    symbols = body.get("symbols")

    if not symbols or not isinstance(symbols, list):
        return jsonify({"ok": False, "error": "symbols list required"}), 400

    headers = get_auth_header()
    if not headers:
        return jsonify({"ok": False, "error": "Auth missing (check FYERS_CLIENT_ID / FYERS_ACCESS_TOKEN)"}), 400

    symbol_str = ",".join(symbols)
    url = f"{FYERS_DATA_BASE}/quotes"

    try:
        res = requests.get(url, headers=headers, params={"symbols": symbol_str}, timeout=5)
        data = res.json()
    except Exception as e:
        return jsonify({"ok": False, "error": f"quote API error: {e}"}), 500

    return jsonify(data)


# ----------------------------------------------------
# FYERS OHLC / HISTORY (15m / 1h / Daily candles)
# ----------------------------------------------------
@app.post("/fyers-ohlc")
def fyers_ohlc():
    """
    Expected JSON:
    {
      "symbol": "NSE:SBIN-EQ",
      "resolution": "15",          # "1","3","5","15","30","60","240","D"
      "date_format": 1,            # 0 = epoch, 1 = yyyy-mm-dd
      "range_from": "2025-11-25",  # depending on date_format
      "range_to":   "2025-11-25",
      "cont_flag": "1"
    }
    """
    body = request.get_json(silent=True) or {}

    symbol = body.get("symbol")
    resolution = body.get("resolution", "15")
    date_format = body.get("date_format", 1)
    range_from = body.get("range_from")
    range_to = body.get("range_to")
    cont_flag = body.get("cont_flag", "1")

    if not symbol:
        return jsonify({"ok": False, "error": "symbol required"}), 400
    if range_from is None or range_to is None:
        return jsonify({"ok": False, "error": "range_from and range_to required"}), 400

    headers = get_auth_header()
    if not headers:
        return jsonify({"ok": False, "error": "Auth missing (check FYERS_CLIENT_ID / FYERS_ACCESS_TOKEN)"}), 400

    url = f"{FYERS_DATA_BASE}/history"
    params = {
        "symbol": symbol,
        "resolution": str(resolution),
        "date_format": str(date_format),
        "range_from": str(range_from),
        "range_to": str(range_to),
        "cont_flag": str(cont_flag),
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=5)
        data = res.json()
    except Exception as e:
        return jsonify({"ok": False, "error": f"history API error: {e}"}), 500

    return jsonify(data)


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
