# Main.py
# RajanTradeAutomation - Render webhook (NSE primary, Yahoo fallback)
from flask import Flask, request, jsonify
import os, requests, time, traceback

app = Flask(__name__)

WEBAPP_EXEC_URL = os.getenv("WEBAPP_EXEC_URL")  # Google Apps Script exec URL
CHARTINK_TOKEN  = os.getenv("CHARTINK_TOKEN", "RAJAN123")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
INTERVAL_SECS   = int(os.getenv("INTERVAL_SECS", "1800"))
TEST_TOKEN      = os.getenv("TEST_TOKEN", "TEST123")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36"

def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print("Telegram send failed:", r.text)
    except Exception as e:
        print("Telegram error:", e)

def gs_post(payload: dict):
    if not WEBAPP_EXEC_URL:
        raise Exception("WEBAPP_EXEC_URL not configured")
    r = requests.post(WEBAPP_EXEC_URL, json=payload, timeout=30)
    try:
        return r.json()
    except:
        return {"ok": False, "raw": r.text}

def fetch_nse_quote(symbol):
    """Try NSE unofficial API first"""
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/"
        }
        # NSE uses symbol without market suffix
        url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
        s = requests.Session()
        s.headers.update(headers)
        # first get home to obtain cookies
        _ = s.get("https://www.nseindia.com", timeout=10)
        r = s.get(url, timeout=10)
        if r.status_code == 200:
            j = r.json()
            if "priceInfo" in j and j["priceInfo"]:
                p = j["priceInfo"]
                return {
                    "price": p.get("lastPrice"),
                    "changePercent": p.get("pChange"),
                    "volume": p.get("totalTradedVolume")
                }
    except Exception as e:
        # ignore and fallback
        print("NSE fetch error for", symbol, e)
    return None

def fetch_yahoo_quote(symbol):
    """Fallback using Yahoo finance (use symbol.NS)"""
    try:
        query = symbol + ".NS"
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={query}"
        r = requests.get(url, timeout=10, headers={"User-Agent": USER_AGENT})
        if r.status_code == 200:
            j = r.json()
            q = j.get("quoteResponse", {}).get("result", [])
            if q:
                rec = q[0]
                return {
                    "price": rec.get("regularMarketPrice"),
                    "changePercent": rec.get("regularMarketChangePercent"),
                    "volume": rec.get("regularMarketVolume")
                }
    except Exception as e:
        print("Yahoo fetch error", symbol, e)
    return None

def get_quote(symbol):
    # Try NSE
    out = fetch_nse_quote(symbol)
    if out and out.get("price") is not None:
        return out
    # fallback Yahoo
    out = fetch_yahoo_quote(symbol)
    return out or {"price": None, "changePercent": None, "volume": None}

@app.post("/chartink-alert")
def chartink_alert():
    try:
        token = request.args.get("token")
        if CHARTINK_TOKEN and token and token != CHARTINK_TOKEN:
            return jsonify({"ok": False, "error": "Invalid Chartink token"}), 403

        data = request.get_json(force=True, silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "Invalid JSON"}), 400

        # normalize stocks (symbols array or comma string)
        stocks = data.get("stocks") or data.get("symbols") or []
        if isinstance(stocks, str):
            stocks = [s.strip() for s in stocks.split(",") if s.strip()]
        if isinstance(stocks, dict):
            stocks = list(stocks.keys())

        detected_count = len(stocks)
        if detected_count == 0:
            send_telegram("📥 Chartink alert received — 0 stocks detected.")
            # forward as empty for logging
            gs_post({"action": "chartink_import", "payload": {"stocks": [], "scanner_name": data.get("scanner_name"), "scanner_url": data.get("scanner_url"), "detected_count": 0}})
            return jsonify({"ok": True, "msg": "No stocks"}), 200

        # de-dup preserving order
        seen = set()
        symbols = []
        for s in stocks:
            sym = s.strip().upper()
            if sym and sym not in seen:
                seen.add(sym)
                symbols.append(sym)

        # fetch quotes (only once per symbol) - can be parallelized later
        enriched = []
        for sym in symbols:
            q = get_quote(sym)
            enriched.append({
                "symbol": sym,
                "price": q.get("price"),
                "changePercent": q.get("changePercent"),
                "volume": q.get("volume")
            })

        payload = {
            "action": "chartink_import",
            "payload": {
                "stocks": enriched,
                "scanner_name": data.get("scanner_name"),
                "scanner_url": data.get("scanner_url"),
                "detected_count": detected_count
            }
        }

        res = gs_post(payload)

        send_telegram(f"📥 Chartink alert received — forwarded to WebApp.\n✅ {detected_count} stocks detected.\nImported (enriched): {len(enriched)}")
        return jsonify({"ok": True, "webapp": res}), 200

    except Exception as e:
        tb = traceback.format_exc()
        send_telegram(f"❌ Render webhook error:\n{e}")
        try:
            gs_post({"action": "phase22_error", "payload": {"message": str(e)}})
        except:
            pass
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/health")
def health():
    return jsonify({"ok": True, "ts": int(time.time())})

if __name__ == "__main__":
    print("Starting RajanTradeAutomation Render Service...")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
