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
# ROOT ROUTE — TEST PURPOSE
# ------------------------------------------------
@app.get("/")
def root():
    return (
        "RajanTradeAutomation is LIVE.<br>"
        "Use <b>/fyers-auth</b> to start Fyers Login Flow.",
        200
    )


# ------------------------------------------------
# STEP 1 — GENERATE AUTH URL
# ------------------------------------------------
@app.get("/fyers-auth")
def fyers_auth():
    try:
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

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ------------------------------------------------
# STEP 2 — RECEIVE AUTH CODE & EXCHANGE TOKEN
# ------------------------------------------------
@app.get("/fyers-redirect")
def fyers_redirect():

    # FIX: Fyers sometimes sends ?auth_code=XXXX instead of ?code=XXXX
    code = request.args.get("auth_code") or request.args.get("code")

    print("Incoming redirect parameters:", dict(request.args))

    if not code or code == "200":
        return (
            "Auth code missing or invalid.<br>"
            f"Received Query Params: {dict(request.args)}",
            400
        )

    print("=====================================")
    print("Received AUTH CODE from FYERS:", code)
    print("=====================================")

    # -------- ACCESS TOKEN REQUEST --------
    token_request = {
        "grant_type": "authorization_code",
        "appId": CLIENT_ID,
        "code": code,
        "secret_key": SECRET_KEY
    }

    try:
        res = requests.post("https://api.fyers.in/api/v3/token", json=token_request)
        
        # FYERS sometimes returns HTML on 503 → avoid JSON parse error
        try:
            token_data = res.json()
        except:
            return (
                f"Token endpoint returned non-JSON response (status={res.status_code}):<br><br>"
                + res.text,
                503
            )

        print("TOKEN RESPONSE:", token_data)
        return jsonify(token_data)

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ------------------------------------------------
# HEALTH CHECK (Render)
# ------------------------------------------------
@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "RajanTradeAutomation"})


# ------------------------------------------------
# START SERVER (Render)
# ------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
