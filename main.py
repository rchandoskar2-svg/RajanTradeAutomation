# Main.py - RajanTradeAutomation (FINAL DEBUG VERSION)
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
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: 
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
    except:
        pass


# ====================================================
#               FULL DEBUG HANDLER
# ====================================================
@app.route('/chartink-alert', methods=['POST'])
def chartink_alert():
    try:
        # Token validation
        token = request.args.get("token","")
        if CHARTINK_TOKEN and token != CHARTINK_TOKEN:
            send_telegram(f"❌ Invalid Chartink token: {token}")
            return jsonify({"ok":False,"error":"invalid token"}), 403

        incoming = request.get_json(force=True, silent=True) or {}
        send_telegram("🔔 Incoming webhook keys: " + ", ".join(list(incoming.keys())[:10]))

        # Chartink Request
        payload = {"scan_clause": SCAN_CLAUSE, "debug_clause": ""}
        safe_headers = HEADERS.copy()
        safe_headers.update({
            "Referer": "https://chartink.com/",
            "Origin": "https://chartink.com",
            "X-Requested-With": "XMLHttpRequest"
        })

        j = {}
        r = None

        # ---- Attempt 1: JSON POST ----
        try:
            r = requests.post(
                "https://chartink.com/screener/process",
                json=payload,
                headers=safe_headers,
                timeout=15
            )
            send_telegram(f"Attempt JSON → status:{r.status_code}, len:{len(r.text)}")
            try:
                j = r.json()
            except Exception as e:
                send_telegram("JSON parse fail(JSON attempt): " + str(e))
        except Exception as e:
            send_telegram("JSON request ERR: " + str(e))

        # ---- Attempt 2: FORM POST ----
        if not j.get("data"):
            try:
                r2 = requests.post(
                    "https://chartink.com/screener/process",
                    data=payload,
                    headers=safe_headers,
                    timeout=15
                )
                send_telegram(f"Attempt FORM → status:{r2.status_code}, len:{len(r2.text)}")
                try:
                    j2 = r2.json()
                except Exception as e:
                    send_telegram("JSON parse fail(FORM attempt): " + str(e))
                    j2 = {}

                if j2.get("data"):
                    j = j2
                    r = r2

            except Exception as e:
                send_telegram("FORM request ERR: " + str(e))

        # ---- Debug keys ----
        data_rows = j.get("data", [])
        send_telegram(f"🔎 Chartink keys: {list(j.keys())[:10]}, data_count={len(data_rows)}")

        # ---- Convert to our stock format ----
        stocks = []
        for item in data_rows:
            sym = item.get("nsecode") or item.get("symbol")
            if not sym:
                continue
            stocks.append({
                "symbol": sym,
                "close": item.get("close"),
                "per_chg": item.get("per_chg"),
                "volume": item.get("volume")
            })

        # ---- Fallback: Parse incoming webhook symbols ----
        if len(stocks) == 0:
            for k in ("symbols","stocks","data","symbols_csv","stock_list"):
                if k in incoming and incoming.get(k):
                    val = incoming[k]

                    if isinstance(val, str):
                        for s in val.split(","):
                            s = s.strip()
                            if s:
                                stocks.append({"symbol": s})

                    elif isinstance(val, list):
                        for it in val:
                            if isinstance(it, str):
                                stocks.append({"symbol": it})
                            elif isinstance(it, dict):
                                sym = it.get("symbol") or it.get("nsecode")
                                if sym:
                                    stocks.append({"symbol": sym})
                    break

        # ---- Prepare GAS payload ----
        post = {
            "action": "chartink_import",
            "payload": {
                "stocks": stocks,
                "scanner_name": os.getenv("SCANNER_NAME", "Rocket Rajan Scanner"),
                "scanner_url": os.getenv("SCANNER_URL", ""),
                "detected_count": len(stocks),
                "chartink_status": r.status_code if r else None,
                "chartink_preview": r.text[:800] if r else None
            }
        }

        # ---- Send to WebApp ----
        if WEBAPP_EXEC_URL:
            try:
                resp = requests.post(WEBAPP_EXEC_URL, json=post, timeout=20)
                send_telegram(
                    f"📥 Forwarded → Detected:{len(stocks)} | WebApp:{resp.status_code}"
                )
                if len(stocks)==0:
                    send_telegram("⚠️ ZERO STOCKS — incoming preview:\n" + str(incoming)[:500])

            except Exception as e:
                send_telegram("❌ WebApp forward ERR: " + str(e))
        else:
            send_telegram("❗ WEBAPP_EXEC_URL missing")

        return jsonify({"ok":True, "detected": len(stocks)})

    except Exception as e:
        send_telegram("❌ Handler error: " + str(e))
        return jsonify({"ok":False,"error":str(e)}), 500



@app.route('/health')
def health():
    return jsonify({"ok":True, "ts": int(time.time())})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
