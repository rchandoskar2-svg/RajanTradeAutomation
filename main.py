# main.py — RajanTradeAutomation (FYERS OAuth v3 helper)
# Replace/Deploy on Render. Ensure requirements.txt contains: flask, requests, fyers-apiv3

from flask import Flask, request, jsonify, redirect
import os
import urllib.parse
import requests
import time
import logging

# Try import fyers library (preferred). If not available, we'll fallback to direct HTTP.
try:
    from fyers_apiv3 import fyersModel
    HAVE_FYERS_SDK = True
except Exception:
    HAVE_FYERS_SDK = False

app = Flask(__name__)

# Setup basic logging so Render logs are informative
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RajanTradeAutomation")

# ------------------------------------------------
# ENVIRONMENT VARIABLES (Render Settings)
# ------------------------------------------------
# IMPORTANT: Set these in Render's Environment (do NOT hardcode secrets in repo)
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")        # e.g. N83MS34FQO-100
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")      # e.g. 9UUVU79KW8
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")  # e.g. https://rajantradeautomation.onrender.com/fyers-redirect

# Optional: Where to save token programmatically (not required)
# If you have an endpoint to store tokens (e.g., Google Apps Script WebApp), set it here.
# STORE_ENDPOINT = os.getenv("TOKEN_STORE_URL")  # optional

# Simple retry helper
def post_with_retries(url, json=None, headers=None, timeout=10, retries=3, backoff=1.0):
    last_exc = None
    for i in range(retries):
        try:
            resp = requests.post(url, json=json, headers=headers, timeout=timeout)
            return resp
        except Exception as e:
            last_exc = e
            logger.warning(f"Post attempt {i+1} failed: {e}. Retrying after {backoff} sec.")
            time.sleep(backoff)
            backoff *= 2
    raise last_exc

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
            logger.error("Missing FYERS environment variables (CLIENT_ID / REDIRECT_URI).")
            return jsonify({"ok": False, "error": "Environment variables missing (FYERS_CLIENT_ID or FYERS_REDIRECT_URI)"}), 500

        encoded_redirect = urllib.parse.quote(REDIRECT_URI, safe='')

        # Use api-t1 endpoint for interactive login (this worked for you earlier)
        auth_url = (
            f"https://api-t1.fyers.in/api/v3/generate-authcode?"
            f"client_id={CLIENT_ID}"
            f"&redirect_uri={encoded_redirect}"
            f"&response_type=code"
            f"&state=rajan_state"
        )

        logger.info(f"Generated auth_url: {auth_url}")
        # Return the URL so you can click it from browser / copy-paste
        return jsonify({"ok": True, "auth_url": auth_url})

    except Exception as e:
        logger.exception("fyers_auth error")
        return jsonify({"ok": False, "error": str(e)}), 500

# ------------------------------------------------
# STEP 2 — RECEIVE AUTH CODE & EXCHANGE TOKEN
# ------------------------------------------------
@app.get("/fyers-redirect")
def fyers_redirect():
    # Fyers will redirect here as: /fyers-redirect?code=XXXX&state=rajan_state
    code = request.args.get("code")
    state = request.args.get("state")

    logger.info(f"Redirect hit. state={state}, code_present={'yes' if code else 'no'}")

    if not code:
        # Fyers sometimes returns HTML or error codes. Return full debug
        msg = "Missing code. Fyers did not return ?code=xxxx — login may not have completed."
        logger.error(msg + f" Full query: {dict(request.args)}")
        return jsonify({"ok": False, "error": msg, "received_query": dict(request.args)}), 400

    # Primary: use fyers-apiv3 SDK if available (recommended)
    if HAVE_FYERS_SDK:
        try:
            logger.info("Using fyers-apiv3 SDK to exchange auth code.")
            session = fyersModel.SessionModel(
                client_id=CLIENT_ID,
                secret_key=SECRET_KEY,
                redirect_uri=REDIRECT_URI,
                response_type="code",
                grant_type="authorization_code"
            )
            session.set_token(code)
            # generate_token() internally calls the token endpoint and returns dict-like response
            response = session.generate_token()
            logger.info("SDK token response received.")
            logger.info(str(response))

            # Optional: store token somewhere safe (see notes below)
            # save_token_somewhere(response)   # implement if you want automatic saving

            return jsonify(response)
        except Exception as e:
            logger.exception("SDK token exchange failed, will attempt HTTP fallback.")
            # fall through to HTTP fallback

    # Fallback: direct POST to token endpoint (json payload)
    try:
        logger.info("Attempting direct HTTP POST to Fyers token endpoint (fallback).")
        token_request = {
            "grant_type": "authorization_code",
            "appId": CLIENT_ID,
            "code": code,
            "secret_key": SECRET_KEY
        }

        token_url = "https://api.fyers.in/api/v3/token"
        resp = post_with_retries(token_url, json=token_request, timeout=10, retries=3, backoff=1.5)

        status = resp.status_code
        logger.info(f"Token endpoint returned status: {status}")

        # If token endpoint returned non-JSON (HTML or 503) — surface the body for debugging
        content_type = resp.headers.get("Content-Type", "")
        body_text = resp.text[:4000]  # limit length

        if status != 200:
            logger.error(f"Token endpoint returned non-200 status: {status}. Body snippet: {body_text}")
            return jsonify({"ok": False, "error": f"Token endpoint returned status {status}", "body_snippet": body_text}), status

        # Try parse JSON
        try:
            token_data = resp.json()
        except Exception as e:
            logger.exception("Failed to parse JSON from token endpoint.")
            return jsonify({"ok": False, "error": "Token endpoint returned non-JSON response", "status": status, "body_snippet": body_text}), 502

        logger.info("Token exchange successful (HTTP fallback).")
        # Optional: store token_data somewhere safe (sheet or env)
        return jsonify(token_data)

    except Exception as e:
        logger.exception("Final token exchange attempt failed.")
        return jsonify({"ok": False, "error": str(e)}), 500

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
    # Local dev port (Render will use its own binding)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
