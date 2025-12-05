from flask import Flask, request, jsonify
import os
import requests

app = Flask(__name__)

# -------------------------------------------------------------------
# ENV VARIABLES
# -------------------------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL")
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

# Health Check
@app.route("/ping", methods=["GET"])
def ping():
    return "PONG", 200

# -------------------------------------------------------------------
# GET SETTINGS (Render → WebApp.gs)
# -------------------------------------------------------------------
@app.route("/getSettings", methods=["GET"])
def get_settings():
    try:
        url = WEBAPP_URL
        payload = {"action": "getSettings", "payload": {}}
        r = requests.post(url, json=payload, timeout=10)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

# -------------------------------------------------------------------
# FYERS REDIRECT HANDLER (OAuth)
# -------------------------------------------------------------------
@app.route("/fyers-redirect", methods=["GET"])
def fyers_redirect():
    try:
        code = request.args.get("auth_code")
        status = request.args.get("status")

        if not code:
            return "Error: Missing auth_code"

        return f"""
        <h3>Status: {status}</h3>
        <p><b>Auth Code:</b></p>
        <textarea rows=6 cols=80>{code}</textarea>
        <p>Copy this code & paste into Render → Environment → FYERS_ACCESS_TOKEN setup step.</p>
        """, 200

    except Exception as e:
        return f"Error: {e}"

# -------------------------------------------------------------------
# PUSH TO WEBAPP.GS (Generic Relay Function)
# -------------------------------------------------------------------
def send_to_webapp(action, payload):
    try:
        r = requests.post(WEBAPP_URL, json={"action": action, "payload": payload}, timeout=10)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

# -------------------------------------------------------------------
# SYNC UNIVERSE (Example call)
# -------------------------------------------------------------------
@app.route("/syncUniverse", methods=["POST"])
def sync_universe():
    payload = request.json
    return jsonify(send_to_webapp("syncUniverse", payload))

# -------------------------------------------------------------------
# UPDATE SECTOR PERFORMANCE
# -------------------------------------------------------------------
@app.route("/updateSectorPerf", methods=["POST"])
def update_sector_perf():
    payload = request.json
    return jsonify(send_to_webapp("updateSectorPerf", payload))

# -------------------------------------------------------------------
# UPDATE STOCK LIST
# -------------------------------------------------------------------
@app.route("/updateStockList", methods=["POST"])
def update_stock_list():
    payload = request.json
    return jsonify(send_to_webapp("updateStockList", payload))

# -------------------------------------------------------------------
# PUSH CANDLE
# -------------------------------------------------------------------
@app.route("/pushCandle", methods=["POST"])
def push_candle():
    payload = request.json
    return jsonify(send_to_webapp("pushCandle", payload))

# -------------------------------------------------------------------
# START SERVER
# -------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
