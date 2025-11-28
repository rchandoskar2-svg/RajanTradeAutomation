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
def send_telegram(msg: str):
    try:
        bot = os.getenv("TELEGRAM_BOT_TOKEN")
        chat = os.getenv("TELEGRAM_CHAT_ID")
        if not bot or not chat:
            return
        url = f"https://api.telegram.org/bot{bot}/sendMessage"
        payload = {"chat_id": chat, "text": msg, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print("Telegram error:", e)


# -----------------------------
# FYERS QUOTES FETCH (ONE-TIME)
# -----------------------------
def fetch_fyers_quotes(symbols):
    """
    symbols: ["NSE:SBIN-EQ", "NSE:TCS-EQ", ...]
    returns: { "NSE:SBIN-EQ": {"price": .., "volume": .., "percent_change": ..}, ... }
    """
    if not symbols:
        return {}

    if not FYERS_ACCESS_TOKEN:
        print("FYERS_ACCESS_TOKEN not set")
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
            print("Fyers response not ok:", data)
            return {}

        out = {}
        for item in data.get("d", []):
            sym = item.get("n")
            v = item.get("v", {}) or {}
            if not sym:
                continue

            out[sym] = {
                "price": v.get("lp"),
                "volume": v.get("v"),
                "percent_change": v.get("chp"),
            }

        return out

    except Exception as e:
        print("Fyers fetch error:", e)
        return {}


# -----------------------------
# API: Apps Script -> Fyers Quotes
# -----------------------------
@app.route("/api/fyers-quotes", methods=["POST"])
def api_fyers_quotes():
    try:
        payload = request.get_json(force=True) or {}
        symbols = payload.get("symbols") or []

        if not isinstance(symbols, list) or not symbols:
            return jsonify({"success": False, "error": "symbols list required"}), 400

        quotes = fetch_fyers_quotes(symbols)

        return jsonify({"success": True, "data": quotes})
    except Exception as e:
        print("/api/fyers-quotes error:", e)
        return jsonify({"success": False, "error": "internal error"}), 500


# -----------------------------
# INTERNAL HANDLER: CHARTINK ALERT
# -----------------------------
def _handle_chartink_alert():
    """
    Common logic for /chartink and /chartink-alert
    """
    try:
        data = request.get_json(force=True) or {}
        symbols = data.get("symbols") or []

        # Telegram log
        if symbols:
            send_telegram("🚀 Chartink Alert Received → " + ", ".join(symbols))

        # Forward raw body to Google Apps Script (WEBAPP_URL)
        if WEBAPP_URL:
            try:
                requests.post(WEBAPP_URL, json=data, timeout=5)
            except Exception as e:
                print("Error forwarding to WebApp:", e)

        return jsonify({"status": "ok"})
    except Exception as e:
        print("chartink handler error:", e)
        send_telegram(f"Chartink handler error: {e}")
        return jsonify({"status": "error"}), 500


# -----------------------------
# PUBLIC ROUTES FOR CHARTINK
# -----------------------------
@app.route("/chartink", methods=["POST"])
def chartink():
    return _handle_chartink_alert()


@app.route("/chartink-alert", methods=["POST"])
def chartink_legacy():
    # Backward compatible route (Chartink अजून इथेच येत आहे)
    return _handle_chartink_alert()


# -----------------------------
# FYERS REDIRECT (AUTH)
# -----------------------------
@app.route("/fyers-redirect")
def fyers_redirect():
    try:
        auth_code = request.args.get("auth_code")
        send_telegram(f"Auth Code Received:\n{auth_code}")
        return "OK"
    except Exception as e:
        print("fyers-redirect error:", e)
        return "ERR"


# -----------------------------
# ROOT
# -----------------------------
@app.route("/")
def home():
    return "RajanTradeAutomation Backend Active."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
