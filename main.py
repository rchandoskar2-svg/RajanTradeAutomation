from flask import Flask, request, jsonify, Response
import requests
import os
import urllib.parse
import json

app = Flask(__name__)

# ------------------------------------------------
# ENVIRONMENT VARIABLES (Render Settings)
# ------------------------------------------------
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")          # Example: N83MS34FQO-100
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
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
                "error": "Environment variables missing (FYERS_CLIENT_ID / FYERS_REDIRECT_URI)."
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
        return jsonify({"ok": False, "error": str(e)}), 500

# ------------------------------------------------
# STEP 2 — RECEIVE AUTH CODE & EXCHANGE TOKEN
# ------------------------------------------------
@app.get("/fyers-redirect")
def fyers_redirect():

    code = request.args.get("code")
    # Some providers may return auth_code under a different param; also log full querystring for debugging:
    print("Full redirect querystring:", request.query_string.decode('utf-8'))

    if not code:
        return (
            "Missing code. Fyers did not return ?code=xxxx<br>"
            "Login was NOT completed.",
            400
        )

    print("=====================================")
    print("Received AUTH CODE from FYERS:", code)
    print("=====================================")

    # -------- Prepare token request payload (JSON) --------
    token_request_json = {
        "grant_type": "authorization_code",
        "appId": CLIENT_ID,
        "code": code,
        "secret_key": SECRET_KEY
    }

    token_url = "https://api.fyers.in/api/v3/token"

    # Try 1: JSON POST (common)
    try:
        print("Token request (JSON) ->", token_request_json)
        res = requests.post(token_url, json=token_request_json, timeout=15)
        print("HTTP status:", res.status_code)
        print("Raw response text (first 1000 chars):", (res.text or "")[:1000])

        # Try decode JSON (safe)
        try:
            token_data = res.json()
            print("Decoded JSON token response keys:", list(token_data.keys()) if isinstance(token_data, dict) else "not-dict")
        except ValueError as jerr:
            # JSON decode failed — show message and attempt fallback
            print("JSON decode failed on first attempt:", jerr)
            token_data = None

    except Exception as e:
        print("Exception during JSON POST to token endpoint:", e)
        res = None
        token_data = None

    # Fallback: if no JSON token_data, try form-encoded POST
    if not token_data:
        try:
            print("Attempting fallback: x-www-form-urlencoded POST")
            form_payload = {
                "grant_type": "authorization_code",
                "appId": CLIENT_ID,
                "code": code,
                "secret_key": SECRET_KEY
            }
            res2 = requests.post(token_url, data=form_payload, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
            print("Fallback HTTP status:", res2.status_code)
            print("Fallback raw response text (first 1000 chars):", (res2.text or "")[:1000])
            try:
                token_data = res2.json()
                print("Fallback decoded JSON keys:", list(token_data.keys()) if isinstance(token_data, dict) else "not-dict")
            except ValueError as jerr2:
                print("Fallback JSON decode failed:", jerr2)
                token_data = None
                # return the raw fallback text to the browser to help debugging
                return Response(f"Token endpoint returned non-JSON response (status={res2.status_code})\n\n{res2.text}", mimetype="text/plain"), 502
        except Exception as e2:
            print("Exception during fallback POST to token endpoint:", e2)
            return jsonify({"ok": False, "error": "Token exchange failed (exception)", "detail": str(e2)}), 502

    # If still no token_data
    if not token_data:
        return jsonify({"ok": False, "error": "Token exchange failed — no valid JSON response from token endpoint"}), 502

    # If successful, persist token temporarily and return to browser
    try:
        # Sanitize write: write to /tmp (Render ephemeral). Do NOT commit secrets to repo.
        try:
            tmp_path = "/tmp/fyers_access.json"
            with open(tmp_path, "w") as fh:
                json.dump(token_data, fh)
            print("Token data saved to", tmp_path)
        except Exception as wf:
            print("Warning: failed to write token to /tmp:", wf)

        # Optionally: echo a small safe summary in browser (avoid printing token raw)
        safe_summary = {
            "ok": True,
            "status": "token_received",
            "has_access_token": ("access_token" in token_data),
            "keys": list(token_data.keys()) if isinstance(token_data, dict) else []
        }
        return jsonify(safe_summary)

    except Exception as e:
        print("Exception saving/returning token data:", e)
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
    app.run(host="0.0.0.0", port=10000)
