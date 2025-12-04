from flask import Flask, request, jsonify
import os
import json
import time
import threading
import requests
from fyers_apiv3 import fyersModel

app = Flask(__name__)

# ----------------------------------------------------
# ENV VARIABLES
# ----------------------------------------------------
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")          # उदा. N83MS34FQO-100
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")    # Render env मधला REDIRECT_URI
ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")    # दररोज नवीन

# तुम्हाला live पाहायचे symbols (सध्या फक्त SBIN)
LIVE_SYMBOLS = ["NSE:SBIN-EQ"]


# ========= HELPER: नवीन Fyers client बनवणे =========
def make_fyers_client():
    global CLIENT_ID, ACCESS_TOKEN
    if not CLIENT_ID or not ACCESS_TOKEN:
        print("❌ make_fyers_client: CLIENT_ID किंवा ACCESS_TOKEN missing आहे")
        return None
    try:
        fy = fyersModel.FyersModel(
            client_id=CLIENT_ID,
            token=ACCESS_TOKEN,
            is_async=False,
            log_path=""
        )
        return fy
    except Exception as e:
        print("❌ make_fyers_client error:", e)
        return None


# ----------------------------------------------------
# ROOT + HEALTH  (UptimeRobot / मनाला शांत)
# ----------------------------------------------------
@app.get("/")
def home():
    return (
        "RajanTradeAutomation ✔ LIVE QUOTES MODE<br>"
        "Routes: /fyers-auth /fyers-redirect /fyers-profile /get-quotes /health"
    )


@app.get("/health")
def health():
    return {"ok": True}


# ----------------------------------------------------
# FYERS AUTH FLOW  (authcode → access_token मिळवण्यासाठी)
# ----------------------------------------------------
@app.get("/fyers-auth")
def fyers_auth():
    if not CLIENT_ID or not REDIRECT_URI:
        return jsonify({"error": "CLIENT_ID किंवा REDIRECT_URI env missing"}), 500

    from urllib.parse import quote
    encoded_redirect = quote(REDIRECT_URI, safe="")
    url = (
        "https://api-t1.fyers.in/api/v3/generate-authcode?"
        f"client_id={CLIENT_ID}"
        f"&redirect_uri={encoded_redirect}"
        f"&response_type=code&state=rajan_state"
    )
    return jsonify({"auth_url": url})


@app.get("/fyers-redirect")
def fyers_redirect():
    """
    Fyers login नंतर redirect इथे येईल.
    access_token JSON मधून दिसेल (तू Render env मध्ये manually टाकतोस).
    """
    auth_code = request.args.get("auth_code") or request.args.get("code")
    if not auth_code:
        return {"error": "No auth code"}, 400

    if not CLIENT_ID or not SECRET_KEY or not REDIRECT_URI:
        return {"error": "SessionModel साठी env missing आहे"}, 500

    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=REDIRECT_URI,
        response_type="code",
        grant_type="authorization_code",
    )

    session.set_token(auth_code)
    response = session.generate_token()
    # यातून "access_token" घेऊन FYERS_ACCESS_TOKEN मध्ये Render env ला टाकायचा.
    return jsonify(response)


# ----------------------------------------------------
# PROFILE TEST  (token valid आहे का तपासण्यासाठी)
# ----------------------------------------------------
@app.get("/fyers-profile")
def fyers_profile():
    if not ACCESS_TOKEN or not CLIENT_ID:
        return {"ok": False, "error": "Token किंवा ClientID missing"}, 400

    headers = {"Authorization": f"{CLIENT_ID}:{ACCESS_TOKEN}"}
    url = "https://api.fyers.in/api/v3/profile"

    try:
        res = requests.get(url, headers=headers, timeout=10)
        try:
            data = res.json()
        except Exception:
            data = {"raw": res.text}
        return {"status_code": res.status_code, "data": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


# ----------------------------------------------------
# GET QUOTES (REST, तुझ्या sample transcript वरून)
# ----------------------------------------------------
@app.get("/get-quotes")
def get_quotes():
    """
    Example: /get-quotes?symbols=NSE:SBIN-EQ,NSE:RELIANCE-EQ
    """
    symbols = request.args.get("symbols")
    if not symbols:
        return {"ok": False, "error": "symbols param missing"}, 400

    fy = make_fyers_client()
    if fy is None:
        return {"ok": False, "error": "Fyers client init failed"}, 500

    data = {"symbols": symbols}
    try:
        response = fy.quotes(data=data)
        return jsonify(response)
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


# ----------------------------------------------------
# LIVE POLLING THREAD (REST quotes → logs मध्ये LIVE data)
# ----------------------------------------------------
def live_quotes_loop():
    """
    WebSocket न वापरता, प्रत्येक 1 सेकंदाला REST quotes() मारतो.
    LIVE_SYMBOLS साठी:
      - open_price
      - high_price
      - low_price
      - lp (LTP)
      - volume
      - atp
      - chp (% change)
    हे logs मध्ये print करतो.
    """
    while True:
        try:
            fy = make_fyers_client()
            if fy is None:
                print("⏸️ Fyers client नाही, 10 सेकंद थांबतो...")
                time.sleep(10)
                continue

            symbols_str = ",".join(LIVE_SYMBOLS)
            data = {"symbols": symbols_str}

            resp = fy.quotes(data=data)
            # resp चे structure transcript सारखे: resp["d"][i]["v"]["lp"] वगैरे
            if not isinstance(resp, dict) or "d" not in resp:
                print("⚠️ Unexpected quotes response:", resp)
            else:
                for item in resp.get("d", []):
                    name = item.get("n", "??")
                    v = item.get("v", {}) or {}
                    lp = v.get("lp")
                    o = v.get("open_price")
                    h = v.get("high_price")
                    l = v.get("low_price")
                    vol = v.get("volume")
                    atp = v.get("atp")
                    chp = v.get("chp")

                    print(
                        f"LIVE {name} → "
                        f"O:{o} H:{h} L:{l} LTP:{lp} "
                        f"VOL:{vol} ATP:{atp} CHP:{chp}"
                    )

        except Exception as e:
            print("❌ live_quotes_loop error:", e)

        # किती वेळाने refresh – आत्ता 1 सेकंद (हवे तर 2-3 सेकंद करु शकतोस)
        time.sleep(1)


# ----------------------------------------------------
# RUN SERVER + BACKGROUND LIVE THREAD
# ----------------------------------------------------
if __name__ == "__main__":
    # LIVE REST feed thread
    t = threading.Thread(target=live_quotes_loop, daemon=True)
    t.start()
    print("✅ Live quotes thread started for:", LIVE_SYMBOLS)

    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
