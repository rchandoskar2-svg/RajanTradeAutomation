from flask import Flask, request, jsonify
import os
import requests
import json

app = Flask(__name__)

WEBAPP_URL = os.getenv("WEBAPP_URL")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")
FYERS_QUOTES_URL = "https://api.fyers.in/data-rest/v3/quotes/"

def fetch_fyers_quotes(symbols):
    if not symbols:
        return {}

    try:
        headers = {"Authorization": f"Bearer {FYERS_ACCESS_TOKEN}"}
        joined = ",".join(symbols)
        r = requests.get(
            FYERS_QUOTES_URL,
            headers=headers,
            params={"symbols": joined},
            timeout=5
        )
        data = r.json()
        if data.get("s") != "ok":
            print("FYERS NOK:", data)
            return {}

        out = {}
        for x in data.get("d", []):
            n = x.get("n")
            v = x.get("v", {}) or {}
            out[n] = {
                "price": v.get("lp"),
                "volume": v.get("v"),
                "percent_change": v.get("chp"),
            }
        return out
    except Exception as e:
        print("fyers error:", e)
        return {}

@app.route("/chartink-alert", methods=["POST"])
def chartink_alert():
    try:
        body = request.get_json(force=True) or {}

        # Forward complete body to WebApp
        if WEBAPP_URL:
            try:
                requests.post(WEBAPP_URL, json=body, timeout=5)
            except Exception as e:
                print("Forward error:", e)

        return jsonify({"ok": True})
    except Exception as e:
        print("chartink error:", e)
        return jsonify({"ok": True})

@app.route("/api/fyers-quotes", methods=["POST"])
def fyers_api():
    body = request.get_json(force=True) or {}
    sy = body.get("symbols") or []
    quotes = fetch_fyers_quotes(sy)
    return jsonify({"data": quotes})

@app.route("/")
def home():
    return "Backend running"
