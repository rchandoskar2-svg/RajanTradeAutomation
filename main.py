# Main.py - RajanTradeAutomation (FINAL SAFE VERSION)
from flask import Flask, request, jsonify
import os, json, requests, traceback, time

app = Flask(__name__)

WEBAPP_EXEC_URL = os.getenv('WEBAPP_EXEC_URL')
CHARTINK_TOKEN   = os.getenv('CHARTINK_TOKEN', 'RAJAN123')
SCAN_CLAUSE      = os.getenv('SCAN_CLAUSE', '( {33492} ( [0] 1 minute close < [0] 1 minute open ) )')
TELEGRAM_TOKEN   = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json"
}

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except:
        pass


@app.route('/chartink-alert', methods=['POST'])
def chartink_alert():
    try:
        token = request.args.get("token","")
        if CHARTINK_TOKEN and token != CHARTINK_TOKEN:
            send_telegram(f"❌ Invalid Chartink token: {token}")
            return jsonify({"ok":False,"error":"invalid token"}), 403

        incoming = request.get_json(force=True, silent=True) or {}

        # --- Chartink process API call with safe headers ---
        payload = { "scan_clause": SCAN_CLAUSE, "debug_clause": "" }
        safe_headers = HEADERS.copy()
        safe_headers.update({
            "Referer": "https://chartink.com/",
            "Origin": "https://chartink.com",
            "X-Requested-With": "XMLHttpRequest"
        })

        try:
            r = requests.post("https://chartink.com/screener/process",
                              json=payload, headers=safe_headers, timeout=15)
            try:
                j = r.json()
            except:
                j = {}
        except Exception as e:
            send_telegram("❌ Chartink API error: " + str(e))
            j = {}

        stocks = []
        for item in j.get("data", []):
            sym = item.get("nsecode") or item.get("symbol")
            if not sym: continue
            stocks.append({
                "symbol": sym,
                "close": item.get("close"),
                "per_chg": item.get("per_chg"),
                "volume": item.get("volume")
            })

        # --- Prepare WebApp payload ---
        post = {
            "action": "chartink_import",
            "payload": {
                "stocks": stocks,
                "scanner_name": os.getenv("SCANNER_NAME", "Rocket Rajan Scanner"),
                "scanner_url": os.getenv("SCANNER_URL", ""),
                "detected_count": len(stocks),
                "incoming_preview": str(incoming)[:400]
            }
        }

        # --- Send to Google Apps Script WebApp ---
        if WEBAPP_EXEC_URL:
            try:
                resp = requests.post(WEBAPP_EXEC_URL, json=post, timeout=20)
                send_telegram(f"📥 Chartink alert → WebApp OK. Detected: {len(stocks)}")
            except Exception as e:
                send_telegram("❌ Failed to forward to WebApp: " + str(e))
        else:
            send_telegram("❗ WEBAPP_EXEC_URL missing")

        return jsonify({"ok":True, "detected": len(stocks)})

    except Exception as e:
        send_telegram("❌ Render webhook error:\n" + str(e))
        return jsonify({"ok":False,"error":str(e)}), 500


@app.route('/health')
def health():
    return jsonify({"ok":True, "ts": int(time.time())})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
