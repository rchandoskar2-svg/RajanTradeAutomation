from flask import Flask, request, jsonify
import os
import requests
import json
import urllib.parse
import threading
import time
import websocket  # websocket-client
from fyers_apiv3 import fyersModel

app = Flask(__name__)

# ----------------------------------------------------
# ENV VARIABLES
# ----------------------------------------------------
CLIENT_ID = os.getenv("FYERS_CLIENT_ID")          # उदा. N83MS34FQO-100
SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
REDIRECT_URI = os.getenv("REDIRECT_URI")
ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")    # रोज अपडेट होणारा token

WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
CHARTINK_TOKEN = os.getenv("CHARTINK_TOKEN", "").strip()

RESPONSE_TYPE = "code"
GRANT_TYPE = "authorization_code"

# Fyers WebSocket endpoint (API v3 data)
FYERS_WS_URL = "wss://api.fyers.in/socket/v2/data/"
# Live feed साठी symbols (तुला हवेले)
FYERS_SYMBOLS = ["NSE:SBIN-EQ", "NSE:RELIANCE-EQ"]


# ----------------------------------------------------
# ROOT
# ----------------------------------------------------
@app.get("/")
def home():
    return (
        "RajanTradeAutomation ACTIVE ✔<br>"
        "Routes: /fyers-auth /fyers-redirect /fyers-profile "
        "/chartink-alert /debug-chartink /health"
    )


# ----------------------------------------------------
# FYERS AUTH FLOW (जुने routes कायम ठेवले)
# ----------------------------------------------------
@app.get("/fyers-auth")
def fyers_auth():
    if not CLIENT_ID or not REDIRECT_URI:
        return jsonify({"error": "Missing CLIENT_ID or REDIRECT_URI"}), 500

    encoded_redirect = urllib.parse.quote(REDIRECT_URI, safe="")
    url = (
        "https://api-t1.fyers.in/api/v3/generate-authcode?"
        f"client_id={CLIENT_ID}"
        f"&redirect_uri={encoded_redirect}"
        f"&response_type={RESPONSE_TYPE}"
        f"&state=rajan_state"
    )
    return jsonify({"auth_url": url})


@app.get("/fyers-redirect")
def fyers_redirect():
    auth_code = request.args.get("auth_code") or request.args.get("code")
    if not auth_code:
        return {"error": "No auth code"}, 400

    if not all([CLIENT_ID, SECRET_KEY, REDIRECT_URI]):
        return {"error": "Missing env for SessionModel"}, 500

    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=REDIRECT_URI,
        response_type=RESPONSE_TYPE,
        grant_type=GRANT_TYPE,
    )

    session.set_token(auth_code)
    response = session.generate_token()
    # इथे मिळालेला access_token तू env मध्ये टाकतोस (Render)
    return jsonify(response)


@app.get("/fyers-profile")
def fyers_profile():
    """
    Test current ACCESS_TOKEN using Fyers profile API.
    """
    if not ACCESS_TOKEN or not CLIENT_ID:
        return jsonify({"ok": False, "error": "Access Token or Client ID Missing"}), 400

    headers = {"Authorization": f"{CLIENT_ID}:{ACCESS_TOKEN}"}
    url = "https://api.fyers.in/api/v3/profile"

    try:
        res = requests.get(url, headers=headers, timeout=10)
        try:
            data = res.json()
        except Exception:
            data = {"raw": res.text}
        return jsonify({"status_code": res.status_code, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ----------------------------------------------------
# CHARTINK DEBUG ROUTE (ठेवले आहे; वापरलास तर)
# ----------------------------------------------------
@app.post("/debug-chartink")
def debug_chartink():
    print("\n========== RAW CHARTINK ALERT (DEBUG) ==========")
    print("Headers:", dict(request.headers))
    try:
        body = request.data.decode(errors="ignore")
    except Exception:
        body = str(request.data)
    print("Body:", body)
    print("===============================================\n")
    return {"ok": True, "msg": "debug logged"}, 200


# ----------------------------------------------------
# MAIN CHARTINK ALERT ROUTE (WebApp.gs साठी forward)
# ----------------------------------------------------
@app.route("/chartink-alert", methods=["GET", "POST"])
def chartink_alert():
    """
    Chartink webhook endpoint → Google Apps Script WebApp forward.
    """
    print("\n====== CHARTINK ALERT HIT ======")
    print("Method:", request.method)
    print("Query args:", dict(request.args))

    incoming_token = request.args.get("token", "").strip()
    if CHARTINK_TOKEN and incoming_token != CHARTINK_TOKEN:
        print("❌ Invalid token:", incoming_token)
        return {"ok": False, "error": "Invalid token"}, 403

    if request.method == "GET":
        print("GET ping received on /chartink-alert → returning pong")
        print("============================================\n")
        return {"ok": True, "msg": "pong"}, 200

    try:
        body_raw = request.data.decode(errors="ignore")
        print("RAW BODY:", body_raw or "[EMPTY]")
        data = json.loads(body_raw) if body_raw else {}
    except Exception as e:
        print("❌ JSON parse error:", str(e))
        return {"ok": False, "error": "Invalid JSON"}, 400

    if not isinstance(data, dict) or "stocks" not in data:
        print("❌ Invalid payload structure, 'stocks' missing")
        print("============================================\n")
        return {"ok": False, "error": "Invalid payload (no stocks)"}, 400

    if not WEBAPP_URL:
        print("❌ WEBAPP_URL not configured in environment")
        return {"ok": False, "error": "WEBAPP_URL not set"}, 500

    try:
        res = requests.post(WEBAPP_URL, json=data, timeout=10)
        print("Forward Response status:", res.status_code)
        print("Forward Response body:", res.text)
    except Exception as e:
        print("❌ FORWARD ERROR:", str(e))
        print("============================================\n")
        return {"ok": False, "error": "Forward failed"}, 500

    print("====== CHARTINK ALERT PROCESSED SUCCESSFULLY ======\n")
    return {"ok": True}, 200


# ----------------------------------------------------
# HEALTH CHECK  (UptimeRobot यालाच ping करेल)
# ----------------------------------------------------
@app.get("/health")
def health():
  return {"ok": True}


# ----------------------------------------------------
# FYERS WEBSOCKET CLIENT (LIVE TICK FEED)
# ----------------------------------------------------
def _on_ws_message(ws, message):
    try:
        data = json.loads(message)
    except Exception:
        print("WS RAW:", message)
        return

    print("WS TICK:", data)


def _on_ws_error(ws, error):
    print("WS ERROR:", error)


def _on_ws_close(ws, status_code, msg):
    print(f"WS CLOSED: {status_code} {msg}")


def _on_ws_open(ws):
    print("WS OPENED → sending subscription...")

    # Fyers docs: wss://api.fyers.in/socket/v2/data/
    # Subscription example:
    # { "symbol": ["NSE:TCS-EQ", "NSE:INFY-EQ"], "type": "symbolUpdate" }
    sub_payload = {
        "symbol": FYERS_SYMBOLS,
        "type": "symbolUpdate"      # किंवा "lite" – तुला full OHLCV हवे असल्याने symbolUpdate
    }

    try:
        ws.send(json.dumps(sub_payload))
        print("WS SUB SENT:", sub_payload)
    except Exception as e:
        print("WS SEND ERROR:", str(e))


def start_fyers_ws_loop():
    """
    Render वर background thread मध्ये चालणारा infinite loop.
    Connection drop झाला तर auto-reconnect करतो.
    """
    if not ACCESS_TOKEN:
        print("❌ FYERS_ACCESS_TOKEN missing – WS client not started")
        return

    # काही implementations header मध्ये Bearer token घेतात.
    # जर इथे auth error आला, logs वरून फॉर्मॅट fine-tune करू.
    headers = [
        f"Authorization: Bearer {ACCESS_TOKEN}",
        f"Client-Id: {CLIENT_ID or ''}"
    ]

    while True:
        try:
            print("Connecting to Fyers WebSocket:", FYERS_WS_URL)
            ws = websocket.WebSocketApp(
                FYERS_WS_URL,
                header=headers,
                on_open=_on_ws_open,
                on_message=_on_ws_message,
                on_error=_on_ws_error,
                on_close=_on_ws_close,
            )
            ws.run_forever(ping_interval=20, ping_timeout=10)
        except Exception as e:
            print("WS CONNECT ERROR:", str(e))

        print("WS reconnecting in 5 seconds...")
        time.sleep(5)


def start_ws_thread_if_possible():
    """
    Flask सुरू होण्याआधी एक daemon thread मध्ये WS सुरू करतो.
    """
    try:
        t = threading.Thread(target=start_fyers_ws_loop, daemon=True)
        t.start()
        print("✅ Fyers WS thread started (daemon=True)")
    except Exception as e:
        print("❌ Unable to start WS thread:", str(e))


# ----------------------------------------------------
# RUN SERVER
# ----------------------------------------------------
if __name__ == "__main__":
    # Live tick feed thread start
    start_ws_thread_if_possible()

    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
