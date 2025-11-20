# RajanTradeAutomation - Stable FYERS Auth + Chartink Enrichment
from flask import Flask, request, jsonify
import os, requests, time, traceback, json

app = Flask(__name__)

# ------------------- ENV -------------------
WEBAPP_EXEC_URL = os.getenv("WEBAPP_EXEC_URL")
CHARTINK_TOKEN  = os.getenv("CHARTINK_TOKEN", "RAJAN123")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")     # e.g. N83M354FQO-100
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY")   # e.g. 9UUVU79KW8
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")  # https://rajantradeautomation.onrender.com/fyers-redirect

USER_AGENT = "Mozilla/5.0"

# Token storage file
TOKEN_FILE = "fyers_token.json"



# ------------------- Telegram -------------------
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: 
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except:
        pass



# ------------------- Google Script Forward -------------------
def gs_post(payload):
    r = requests.post(WEBAPP_EXEC_URL, json=payload, timeout=20)
    try:
        return r.json()
    except:
        return {"raw": r.text}



# ------------------- NSE BASIC FETCH (same as old) -------------------
def fetch_nse_quote(symbol):
    try:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT})

        _ = s.get("https://www.nseindia.com", timeout=8)
        r = s.get(f"https://www.nseindia.com/api/quote-equity?symbol={symbol}", timeout=8)

        if r.status_code == 200:
            j = r.json()
            p = j.get("priceInfo", {})
            return {
                "price": p.get("lastPrice"),
                "changePercent": p.get("pChange"),
                "volume": p.get("totalTradedVolume")
            }
    except:
        pass
    return None


def fetch_yahoo_quote(symbol):
    try:
        q = symbol + ".NS"
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={q}"
        r = requests.get(url, timeout=8, headers={"User-Agent": USER_AGENT})
        j = r.json()["quoteResponse"]["result"]
        if j:
            rec = j[0]
            return {
                "price": rec.get("regularMarketPrice"),
                "changePercent": rec.get("regularMarketChangePercent"),
                "volume": rec.get("regularMarketVolume")
            }
    except:
        pass
    return None


def get_quote(symbol):
    out = fetch_nse_quote(symbol)
    if out and out["price"] is not None:
        return out
    out = fetch_yahoo_quote(symbol)
    return out or {"price": None, "changePercent": None, "volume": None}



# ------------------- FYERS AUTH (Stable version) -------------------
@app.get("/fyers-auth")
def fyers_auth():
    try:
        if not FYERS_CLIENT_ID or not FYERS_REDIRECT_URI:
            return jsonify({"ok": False, "error": "Missing FYERS env vars"}), 400

        # VERY IMPORTANT → Correct encoded redirect_uri
        redirect_encoded = requests.utils.quote(FYERS_REDIRECT_URI, safe='')

        auth_url = (
            f"https://api-t1.fyers.in/api/v3/generate-authcode"
            f"?client_id={FYERS_CLIENT_ID}"
            f"&redirect_uri={redirect_encoded}"
            f"&response_type=code&state=rajan_state"
        )

        return jsonify({"ok": True, "auth_url": auth_url})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500



@app.get("/fyers-redirect")
def fyers_redirect():
    try:
        code = request.args.get("code")
        if not code:
            return "Missing code", 400

        # generate access_token
        payload = {
            "grant_type": "authorization_code",
            "appId": FYERS_CLIENT_ID,
            "secret_key": FYERS_SECRET_KEY,
            "code": code,
            "redirect_uri": FYERS_REDIRECT_URI
        }

        r = requests.post(
            "https://api.fyers.in/api/v3/token",
            json=payload,
            headers={"Content-Type": "application/json"}
        )

        data = r.json()

        # save file
        with open(TOKEN_FILE, "w") as f:
            json.dump(data, f)

        send_telegram("✅ FYERS Token Generated & Saved Successfully")

        return "Auth Completed. Token saved."

    except Exception as e:
        send_telegram("❌ FYERS Redirect Error: " + str(e))
        return "Error: " + str(e), 500



# ------------------- CHARTINK ROUTE -------------------
@app.post("/chartink-alert")
def chartink_alert():
    try:
        data = request.get_json(force=True) or {}
        stocks = data.get("stocks", [])

        if isinstance(stocks, str):
            stocks = [s.strip() for s in stocks.split(",")]

        final = []
        for sym in stocks:
            q = get_quote(sym)
            final.append({
                "symbol": sym,
                "price": q["price"],
                "changePercent": q["changePercent"],
                "volume": q["volume"]
            })

        payload = {
            "action": "chartink_import",
            "payload": {
                "stocks": final,
                "scanner_name": data.get("scanner_name"),
                "scanner_url": data.get("scanner_url"),
                "detected_count": len(stocks)
            }
        }

        gs_post(payload)
        return {"ok": True}

    except Exception as e:
        send_telegram("❌ Chartink Import Error: " + str(e))
        return {"ok": False, "error": str(e)}, 500



@app.get("/health")
def health():
    return {"ok": True, "ts": int(time.time())}



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
