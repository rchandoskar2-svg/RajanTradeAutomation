from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

# -----------------------------
# ENVIRONMENT VARIABLES
# -----------------------------
CHARTINK_TOKEN = os.getenv("CHARTINK_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")

FYERS_QUOTES_URL = "https://api.fyers.in/data-rest/v3/quotes/"

# -----------------------------
# TELEGRAM
# -----------------------------
def send_telegram(msg):
    try:
        bot = os.getenv("TELEGRAM_BOT_TOKEN")
        chat = os.getenv("TELEGRAM_CHAT_ID")
        if not bot or not chat:
            return
        url = f"https://api.telegram.org/bot{bot}/sendMessage"
        payload = {"chat_id": chat, "text": msg, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=3)
    except:
        pass

# -----------------------------
# FYERS QUOTES FETCH (ONE-TIME)
# -----------------------------
def fetch_fyers_quotes(symbols):
    if not symbols:
        return {}

    headers = {
        "Authorization": f"Bearer {FYERS_ACCESS_TOKEN}"
    }

    try:
        joined = ",".join(symbols)
        params = {"symbols": joined}

        resp = requests.get(FYERS_QUOTES_URL, headers=headers, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        if data.get("s") != "ok":
            return {}

        out = {}

        for item in data.get("d", []):
            sym = item.get("n")
            v = item.get("v", {})

            out[sym] = {
                "price": v.get("lp"),
                "volume": v.get("v"),
                "percent_change": v.get("chp")
            }

        return out

    except Exception as e:
        print(f"Fyers fetch error: {e}")
        return {}

# -----------------------------
# API ROUTE → APPS SCRIPT CALLS HERE
# -----------------------------
@app.route("/api/fyers-quotes", methods=["POST"])
def api_fyers_quotes():
    try:
        payload = request.get_json(force=True)
        symbols = payload.get("symbols", [])

        quotes = fetch_fyers_quotes(symbols)

        return jsonify({
            "success": True,
            "data": quotes
        })

    except Exception as e:
        print(f"/api/fyers-quotes error: {e}")
        return jsonify({"success": False, "error": "Internal error"}), 500


# -----------------------------
# CHARTINK ALERT → Forward To Sheets
# -----------------------------
@app.route("/chartink", methods=["POST"])
def chartink():
    try:
        data = request.get_json(force=True)
        send_telegram(f"🚀 Chartink Alert → {', '.join(data.get('symbols', []))}")

        # PUSH TO WEBAPP (SHEETS)
        requests.post(WEBAPP_URL, json=data, timeout=3)

        return jsonify({"status": "ok"})

    except Exception as e:
        send_telegram(f"Chartink Error: {e}")
        return jsonify({"status": "error"}), 500


# -----------------------------
# FYERS REDIRECT (AUTH)
# -----------------------------
@app.route("/fyers-redirect")
def fyers_redirect():
    try:
        auth_code = request.args.get("auth_code")
        send_telegram(f"Auth Code Received:\n{auth_code}")
        return "OK"
    except:
        return "ERR"


# -----------------------------
# MAIN
# -----------------------------
@app.route("/")
def home():
    return "RajanTradeAutomation Backend Active."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
