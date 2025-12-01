from flask import Flask, request, jsonify
import requests
import os
import json
from urllib.parse import parse_qs

app = Flask(__name__)

# -----------------------------------------------------------------
# ENVIRONMENT VARIABLES
# -----------------------------------------------------------------
WEBAPP_URL = os.getenv("WEBAPP_URL")
FYERS_QUOTES_URL = "https://api.fyers.in/data-rest/v3/quotes/"

# -----------------------------------------------------------------
# TELEGRAM
# -----------------------------------------------------------------
def send_telegram(msg):
    try:
        bot = os.getenv("TELEGRAM_BOT_TOKEN")
        chat = os.getenv("TELEGRAM_CHAT_ID")
        if not bot or not chat:
            return

        requests.post(
            f"https://api.telegram.org/bot{bot}/sendMessage",
            json={"chat_id": chat, "text": msg},
            timeout=5
        )
    except Exception as e:
        print("Telegram error:", e)


# -----------------------------------------------------------------
# FYERS QUOTES — SAFE + DEBUG
# -----------------------------------------------------------------
def fetch_fyers_quotes(symbols):
    if not symbols:
        print("No symbols requested for quotes")
        return {}

    # READ TOKEN EVERY CALL (IMPORTANT!)
    token = os.getenv("FYERS_ACCESS_TOKEN")
    if not token:
        print("NO FYERS TOKEN IN ENV")
        return {}

    headers = {
        "Authorization": f"Bearer {token}"
    }

    try:
        joined = ",".join(symbols)

        r = requests.get(
            FYERS_QUOTES_URL,
            headers=headers,
            params={"symbols": joined},
            timeout=5,
        )

        # Debug — always print
        print("Fyers HTTP Status:", r.status_code)
        print("Fyers RAW Response:", r.text[:250])

        # Parse JSON safely
        try:
            data = r.json()
        except Exception as je:
            print("JSON Parse Error:", je)
            return {}

        if data.get("s") != "ok":
            print("Fyers NOT OK:", data)
            return {}

        # Extract results
        out = {}
        for it in data.get("d", []):
            sym = it.get("n")
            v = it.get("v", {}) or {}

            out[sym] = {
                "price": v.get("lp"),
                "volume": v.get("v"),
                "percent_change": v.get("chp"),
            }

        return out

    except Exception as e:
        print("Fyers error:", e)
        return {}


# -----------------------------------------------------------------
# CHARTINK HANDLER — FINAL ROBUST VERSION
# -----------------------------------------------------------------
def _handle_chartink_alert():
    try:
        raw = request.get_data(as_text=True) or ""
        data = {}

        # Try JSON
        try:
            data = json.loads(raw)
        except:
            pass

        # Fallback — form encoded
        if not isinstance(data, dict) or not data:
            try:
                parsed = parse_qs(raw)
                if "stocks" in parsed:
                    data["stocks"] = parsed["stocks"][0]
                if "trigger_prices" in parsed:
                    data["trigger_prices"] = parsed["trigger_prices"][0]
            except Exception as e:
                print("Parse fallback error:", e)

        # Extract symbols
        symbols = data.get("symbols") or []

        if not symbols and "stocks" in data:
            raw_s = data.get("stocks", "")
            symbols = [x.strip() for x in raw_s.split(",") if x.strip()]

        # Telegram
        if symbols:
            send_telegram("🚀 Chartink Alert Received → " + ", ".join(symbols))

        # Forward to Google WebApp
        if WEBAPP_URL:
            try:
                requests.post(WEBAPP_URL, json=data, timeout=5)
            except Exception as e:
                print("Forward error:", e)

        return jsonify({"status": "ok"})

    except Exception as e:
        print("CHARTINK ERROR:", e)
        return jsonify({"status": "ok"})


# -----------------------------------------------------------------
# ROUTES
# -----------------------------------------------------------------
@app.route("/chartink", methods=["POST"])
def chartink():
    return _handle_chartink_alert()


@app.route("/chartink-alert", methods=["POST"])
def chartink_alert():
    return _handle_chartink_alert()


@app.route("/api/fyers-quotes", methods=["POST"])
def fyers_quotes():
    try:
        payload = request.get_json(force=True) or {}
        symbols = payload.get("symbols") or []

        data = fetch_fyers_quotes(symbols)

        return jsonify({"success": True, "data": data})

    except Exception as e:
        print("Fyers quotes route error:", e)
        return jsonify({"success": False, "data": {}}), 200


@app.route("/")
def home():
    return "RajanTradeAutomation Backend ACTIVE."


# -----------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
