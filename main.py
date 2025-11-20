from flask import Flask, request, jsonify
import os, requests, json, traceback

from fyers_apiv3 import fyersModel

app = Flask(__name__)

# ----------------- ENV VARS ------------------------
FYERS_CLIENT_ID   = os.getenv("FYERS_CLIENT_ID")
FYERS_SECRET_KEY  = os.getenv("FYERS_SECRET_KEY")
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")  # MUST MATCH EXACT
FYERS_TOKEN_FILE  = "fyers_token.json"


# ----------------- SAVE TOKEN ------------------------
def save_fyers_tokens(data):
    try:
        with open(FYERS_TOKEN_FILE, "w") as f:
            json.dump(data, f)
        return True
    except:
        return False


# ------------------------------------------------------
#   1) GET AUTH URL
# ------------------------------------------------------
@app.get("/fyers-auth")
def fyers_auth():
    try:
        session = fyersModel.SessionModel(
            client_id=FYERS_CLIENT_ID,
            secret_key=FYERS_SECRET_KEY,
            redirect_uri=FYERS_REDIRECT_URI,
            response_type="code",
            state="rajan_state"
        )
        auth_url = session.generate_authcode()
        return jsonify({"ok": True, "auth_url": auth_url})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ------------------------------------------------------
#   2) REDIRECT → EXCHANGE CODE FOR TOKEN
# ------------------------------------------------------
@app.get("/fyers-redirect")
def fyers_redirect():
    try:
        auth_code = request.args.get("code")

        if not auth_code:
            return "Missing code", 400

        session = fyersModel.SessionModel(
            client_id=FYERS_CLIENT_ID,
            secret_key=FYERS_SECRET_KEY,
            redirect_uri=FYERS_REDIRECT_URI,
            response_type="code",
            grant_type="authorization_code"
        )

        session.set_token(auth_code)
        token = session.generate_token()

        save_fyers_tokens(token)

        return "FYERS Auth Successful! Token saved."
    except Exception as e:
        return f"Auth error: {e}", 500


@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
