# ============================================================
#  RajanTradeAutomation - FINAL STABLE main.py
#  Fyers Auth (using api-t1) + Live Data + Chartink Webhook
# ============================================================

from flask import Flask, request, jsonify
import os, requests, time, traceback, json

app = Flask(__name__)

# ------------------- ENV -------------------
WEBAPP_EXEC_URL = os.getenv("WEBAPP_EXEC_URL")

CHARTINK_TOKEN  = os.getenv("CHARTINK_TOKEN", "RAJAN123")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# FYERS
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID", "")
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY", "")
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI", "")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN", "")

TOKEN_FILE = "fyers_token.json"


# ------------------- TELEGRAM -------------------
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram missing")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except:
        pass


# ------------------- GAS POST -------------------
def gs_post(payload):
    r = requests.post(WEBAPP_EXEC_URL, json=payload, timeout=20)
    try:
        return r.json()
    except:
        return {"ok": False, "raw": r.text}


# ------------------- SAVE FYERS TOKEN -------------------
def save_access_token(token):
    try:
        with open(TOKEN_FILE, "w") as f:
            json.dump({"access_token": token}, f)
        os.environ["FYERS_ACCESS_TOKEN"] = token
        return True
    except:
        return False


# ------------------- LOAD FYERS TOKEN -------------------
def load_access_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            return json.load(f).get("access_token")
    return ""


# ------------------- FYERS AUTH URL -------------------
@app.get("/fyers-auth")
def fyers_auth():
    try:
        if not FYERS_CLIENT_ID or not FYERS_SECRET_KEY or not FYERS_REDIRECT_URI:
            return jsonify({"ok": False, "error": "Env missing"}), 400

        state = "rajan_state"

        # FINAL WORKING URL → YOU CONFIRMED
        auth_url = (
            "https://api-t1.fyers.in/api/v3/generate-authcode?"
            f"client_id={FYERS_CLIENT_ID}&"
            f"redirect_uri={requests.utils.quote(FYERS_REDIRECT_URI)}&"
            f"response_type=code&state={state}"
        )

        return jsonify({"ok": True, "auth_url": auth_url})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ------------------- FYERS REDIRECT -------------------
@app.get("/fyers-redirect")
def fyers_redirect():
    try:
        code = request.args.get("auth_code") or request.args.get("code")
        if not code:
            return "Missing code", 400

        # Exchange auth_code → access_token
        url = "https://api.fyers.in/api/v3/validate-authcode"
        payload = {
            "grant_type": "authorization_code",
            "appId": FYERS_CLIENT_ID,
            "appSecret": FYERS_SECRET_KEY,
            "auth_code": code
        }

        r = requests.post(url, json=payload, timeout=15).json()

        if "access_token" not in r:
            send_telegram(f"❌ FYERS Token Error:\n{r}")
            return f"Token error: {r}", 500

        access_token = r["access_token"]
        save_access_token(access_token)

        send_telegram("✅ FYERS Access Token saved successfully.")
        return "Authentication Success. Token Saved.", 200

    except Exception as e:
        return f"Error: {e}", 500


# ------------------- GET QUOTE (NSE → Yahoo fallback) -------------------
def fetch_nse(symbol):
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        s = requests.Session()
        s.headers.update(headers)
        _ = s.get("https://www.nseindia.com", timeout=10)
        url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
        r = s.get(url, timeout=10)
        if r.status_code == 200:
            j = r.json()
            p = j.get("priceInfo", {})
            return {
                "price": p.get("lastPrice"),
                "changePercent": p.get("pChange"),
                "volume": p.get("totalTradedVolume"),
                "low": p.get("intraDayLow"),
                "high": p.get("intraDayHigh")
            }
    except:
        pass
    return None


def fetch_yahoo(symbol):
    try:
        q = symbol + ".NS"
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={q}"
        r = requests.get(url, timeout=10)
        j = r.json().get("quoteResponse", {}).get("result", [])
        if j:
            rec = j[0]
            return {
                "price": rec.get("regularMarketPrice"),
                "changePercent": rec.get("regularMarketChangePercent"),
                "volume": rec.get("regularMarketVolume"),
                "low": rec.get("regularMarketDayLow"),
                "high": rec.get("regularMarketDayHigh")
            }
    except:
        pass
    return None


def get_quote(symbol):
    out = fetch_nse(symbol)
    if out and out.get("price"):
        return out
    out = fetch_yahoo(symbol)
    return out or {"price": None, "changePercent": None, "volume": None}


# ------------------- CHARTINK ALERT -------------------
@app.post("/chartink-alert")
def chartink_alert():
    try:
        token = request.args.get("token")
        if token and token != CHARTINK_TOKEN:
            return jsonify({"ok": False, "error": "Bad token"}), 403

        data = request.get_json(force=True, silent=True) or {}
        stocks = data.get("stocks") or data.get("symbols") or []

        if isinstance(stocks, str):
            stocks = [s.strip() for s in stocks.split(",") if s.strip()]

        if not stocks:
            gs_post({"action": "chartink_import", "payload": {"stocks": []}})
            return jsonify({"ok": True, "msg": "0 stocks"}), 200

        symbols = []
        seen = set()
        for s in stocks:
            s = s.upper().strip()
            if s not in seen:
                seen.add(s)
                symbols.append(s)

        # Fetch prices
        enriched = []
        for sym in symbols:
            q = get_quote(sym)
            enriched.append({
                "symbol": sym,
                "price": q["price"],
                "changePercent": q["changePercent"],
                "volume": q["volume"]
            })

        payload = {
            "action": "chartink_import",
            "payload": {"stocks": enriched}
        }

        res = gs_post(payload)
        send_telegram(f"📥 Imported {len(enriched)} stocks")

        return jsonify({"ok": True, "webapp": res}), 200

    except Exception as e:
        send_telegram(f"❌ Error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/health")
def health():
    return jsonify({"ok": True, "ts": int(time.time())})


if __name__ == "__main__":
    print("Starting RajanTradeAutomation (FINAL BUILD)...")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
