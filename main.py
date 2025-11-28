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
# INTERNAL HANDLER FOR CHARTINK
# -----------------------------
def _handle_chartink_alert():
    try:
        data = request.get_json(force=True) or {}

        # ------------------------
        # FIX: Read Chartink STOCKS
        # ------------------------
        symbols = data.get("symbols") or []

        if (not symbols) and ("stocks" in data):
            raw = data["stocks"]
            if isinstance(raw, str):
                symbols = [s.strip() for s in raw.split(",") if s.strip()]

        # Telegram
        if symbols:
            send_telegram("🚀 Chartink Alert Received → " + ", ".join(symbols))

        # Forward raw payload to Sheets WebApp
        if WEBAPP_URL:
            requests.post(WEBAPP_URL, json=data, timeout=5)

        return jsonify({"status": "ok"})

    except Exception as e:
        print("chartink handler error:", e)
        send_telegram(f"Chartink handler error: {e}")
        return jsonify({"status": "error"}), 500


# PUBLIC ROUTES
@app.route("/chartink", methods=["POST"])
def chartink():
    return _handle_chartink_alert()

@app.route("/chartink-alert", methods=["POST"])
def chartink_legacy():
    return _handle_chartink_alert()


# -----------------------------
# API: FYERS QUOTES
# -----------------------------
@app.route("/api/fyers-quotes", methods=["POST"])
def api_fyers_quotes():
    try:
        payload = request.get_json(force=True) or {}
        symbols = payload.get("symbols") or []

        quotes = fetch_fyers_quotes(symbols)

        return jsonify({"success": True, "data": quotes})
    except Exception as e:
        print("/api/fyers-quotes error:", e)
        return jsonify({"success": False, "error": "internal error"}), 500


@app.route("/")
def home():
    return "RajanTradeAutomation Backend Active."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
