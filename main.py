"""
RajanTradeAutomation - Kushal Strategy Server (v1.5)
- /run_strategy आता आधी WebApp कडून settings वाचतो
- नंतर sample (dummy) universe वर तुझ्या %move rules apply करून
  WebApp ला Chartink-style payload POST करतो.
"""

import os
import json
import urllib.parse
from datetime import datetime

from flask import Flask, request, jsonify
import requests
from fyers_apiv3 import fyersModel

app = Flask(__name__)

# ----------------------------------------------------
# ENV VARIABLES
# ----------------------------------------------------
CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "").strip()
SECRET_KEY = os.getenv("FYERS_SECRET_KEY", "").strip()
REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI", "").strip()
ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "").strip()
REFRESH_TOKEN = os.getenv("FYERS_REFRESH_TOKEN", "").strip()

WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()   # Google Apps Script exec URL
MODE = os.getenv("MODE", "SIM").strip()            # SIM / LIVE (future use)

try:
    INTERVAL_SECS = int(os.getenv("INTERVAL_SECS", "1800").strip() or "1800")
except Exception:
    INTERVAL_SECS = 1800

RESPONSE_TYPE = "code"
GRANT_TYPE = "authorization_code"


# ----------------------------------------------------
# ROOT + HEALTH
# ----------------------------------------------------
@app.get("/")
def home():
    return (
        "RajanTradeAutomation ACTIVE ✔<br>"
        "Routes: /health /fyers-auth /fyers-profile /test_symbol /run_strategy"
    )


@app.get("/health")
def health():
    return {
        "ok": True,
        "mode": MODE,
        "interval_secs": INTERVAL_SECS
    }, 200


# ----------------------------------------------------
# FYERS AUTH / PROFILE / TEST
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

    if not (CLIENT_ID and SECRET_KEY and REDIRECT_URI):
        return {"error": "Missing CLIENT_ID / SECRET_KEY / REDIRECT_URI"}, 500

    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=REDIRECT_URI,
        response_type=RESPONSE_TYPE,
        grant_type=GRANT_TYPE,
    )

    session.set_token(auth_code)
    response = session.generate_token()
    return jsonify(response)


@app.get("/fyers-profile")
def fyers_profile():
    if not ACCESS_TOKEN or not CLIENT_ID:
        return {"ok": False, "error": "Access Token or Client ID Missing"}, 400

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


@app.get("/test_symbol")
def test_symbol():
    symbol = request.args.get("symbol", "").strip()
    if not symbol:
        return jsonify({"ok": False, "error": "symbol param missing"}), 400

    if not ACCESS_TOKEN or not CLIENT_ID:
        return jsonify({"ok": False, "error": "Access Token or Client ID Missing"}), 400

    headers = {"Authorization": f"{CLIENT_ID}:{ACCESS_TOKEN}"}
    url = "https://api.fyers.in/data-rest/v2/quotes/"
    params = {"symbols": symbol}

    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        try:
            data = res.json()
        except Exception:
            data = {"raw": res.text}
        return jsonify({
            "ok": True,
            "symbol": symbol,
            "status_code": res.status_code,
            "data": data
        }), 200
    except Exception as e:
        return jsonify({
            "ok": False,
            "symbol": symbol,
            "error": str(e)
        }), 500


# ----------------------------------------------------
# HELPER: Fetch settings from WebApp
# ----------------------------------------------------
def fetch_settings():
    """
    WebApp.gs doGet?action=getSettings मधून settings JSON वाचतो.
    """
    if not WEBAPP_URL:
        return {"ok": False, "error": "WEBAPP_URL not configured"}

    url = WEBAPP_URL
    if "?" in url:
        url = url + "&action=getSettings"
    else:
        url = url + "?action=getSettings"

    try:
        res = requests.get(url, timeout=10)
        data = res.json()
    except Exception as e:
        return {"ok": False, "error": f"GET settings failed: {e}"}

    if not data.get("ok"):
        return {"ok": False, "error": f"Settings error: {data}"}

    settings = data.get("settings", {})
    return {"ok": True, "settings": settings, "raw": data}


# ----------------------------------------------------
# HELPER: Dummy universe + strategy skeleton
# ----------------------------------------------------
def build_dummy_signals(settings, bias="BUY"):
    """
    सध्या data नसल्यामुळे static universe आणि %change वापरून
    तुझ्या logic नुसार signals बनवतो.
    नंतर इथे real Fyers data plug करू.
    """

    min_move = float(settings.get("MIN_MOVE_THRESHOLD", 2.5))
    max_stocks = int(settings.get("MAX_STOCKS", 3))

    # dummy sector wise universe with %change
    # भविष्यात इथे FnO universe + real %change येईल.
    if bias == "BUY":
        # top gainer sector = BANKING (उदा.)
        universe = [
            {"symbol": "ICICIBANK", "pct": 1.2},
            {"symbol": "HDFCBANK", "pct": 2.4},
            {"symbol": "AXISBANK", "pct": 3.1},
            {"symbol": "SBIN", "pct": 0.8},
        ]
        # rule: 0 < pct <= min_move
        filtered = [
            s for s in universe
            if 0 < s["pct"] <= min_move
        ]
    else:
        # bias = SELL, top loser sector = IT (उदा.)
        universe = [
            {"symbol": "INFY", "pct": -1.1},
            {"symbol": "TCS", "pct": -2.0},
            {"symbol": "WIPRO", "pct": -3.5},
            {"symbol": "TECHM", "pct": -0.6},
        ]
        # rule: -min_move <= pct < 0
        filtered = [
            s for s in universe
            if -min_move <= s["pct"] < 0
        ]

    # MAX_STOCKS limit
    filtered = filtered[:max_stocks]

    # dummy trigger prices: assume LTP approx
    signals = []
    for s in filtered:
        # फक्त demo साठी काही approximate prices
        base_price = {
            "ICICIBANK": 950,
            "HDFCBANK": 1600,
            "AXISBANK": 1200,
            "SBIN": 800,
            "INFY": 1500,
            "TCS": 3800,
            "WIPRO": 450,
            "TECHM": 1350,
        }.get(s["symbol"], 100)

        # %change apply करून approximate price
        price = round(base_price * (1 + s["pct"] / 100), 2)
        signals.append({"symbol": s["symbol"], "price": price})

    return signals


# ----------------------------------------------------
# MAIN STRATEGY ROUTE
# ----------------------------------------------------
@app.post("/run_strategy")
def run_strategy():
    """
    Step-2:
    - Settings WebApp मधून fetch करतो
    - dummy universe वर तुझ्या %move logic ने signals बनवतो
    - Chartink-style payload WebApp.gs कडे POST करतो
    """

    now_ist = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    if not WEBAPP_URL:
        return jsonify({
            "ok": False,
            "error": "WEBAPP_URL not configured in env",
            "mode": MODE
        }), 500

    # 1) Settings fetch
    settings_result = fetch_settings()
    if not settings_result.get("ok"):
        return jsonify({
            "ok": False,
            "error": settings_result.get("error"),
            "mode": MODE
        }), 500

    settings = settings_result["settings"]

    # 2) फिलहाल bias fixed ठेवू (उदा. BUY).
    # पुढे market breadth वरून BUY/SELL ठरवू.
    bias = "BUY"

    # 3) Dummy universe वरून signals
    signals = build_dummy_signals(settings, bias=bias)

    if not signals:
        demo_payload = {
            "stocks": "",
            "trigger_prices": "",
            "triggered_at": now_ist,
            "scan_name": f"KUSHAL_{bias}_{MODE}",
            "source": "RajanTradeAutomation_no_signals"
        }
    else:
        stocks = ",".join(s["symbol"] for s in signals)
        prices = ",".join(str(s["price"]) for s in signals)
        demo_payload = {
            "stocks": stocks,
            "trigger_prices": prices,
            "triggered_at": now_ist,
            "scan_name": f"KUSHAL_{bias}_{MODE}",
            "source": "RajanTradeAutomation_signals"
        }

    # 4) WebApp ला forward
    try:
        res = requests.post(
            WEBAPP_URL,
            json=demo_payload,
            timeout=10
        )
        forward_status = res.status_code
        forward_body = res.text
    except Exception as e:
        forward_status = -1
        forward_body = str(e)

    return jsonify({
        "ok": True,
        "mode": MODE,
        "interval_secs": INTERVAL_SECS,
        "webapp_url_present": bool(WEBAPP_URL),
        "settings": settings,
        "bias": bias,
        "signals": signals,
        "webapp_forward_status": forward_status,
        "webapp_forward_body": forward_body
    }), 200


# (Render gunicorn entrypoint खाली जसाच्या तसा राहू दे)
