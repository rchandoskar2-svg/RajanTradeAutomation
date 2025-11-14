# Main.py - RajanTradeAutomation (FINAL)
from flask import Flask, request, jsonify
import os, json, requests, time, traceback

app = Flask(__name__)

WEBAPP_EXEC_URL = os.getenv('WEBAPP_EXEC_URL')
CHARTINK_TOKEN = os.getenv('CHARTINK_TOKEN', 'RAJAN123')
SCAN_CLAUSE = os.getenv('SCAN_CLAUSE', '( {33492} ( [0] 1 minute close < [0] 1 minute open ) )')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN','')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID','')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Content-Type': 'application/json'
}

def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    try:
        requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': text}, timeout=10)
    except:
        pass

@app.route('/chartink-alert', methods=['POST'])
def chartink_alert():
    try:
        token = request.args.get('token','')
        if CHARTINK_TOKEN and token != CHARTINK_TOKEN:
            send_telegram(f'❌ Invalid Chartink token received: {token}')
            return jsonify({'ok':False,'error':'invalid token'}),403

        data = request.get_json(force=True, silent=True) or {}
        # Chartink webhook often sends symbol list or basic payload; we'll call process API to enrich

        # Call Chartink process API
        payload = {'scan_clause': SCAN_CLAUSE, 'debug_clause': ''}
        try:
            r = requests.post('https://chartink.com/screener/process', json=payload, headers=HEADERS, timeout=15)
            j = r.json() if r.status_code==200 else {}
        except Exception as e:
            j = {}

        stocks = []
        for item in j.get('data', []):
            sym = item.get('nsecode') or item.get('symbol')
            stocks.append({
                'symbol': sym,
                'close': item.get('close'),
                'per_chg': item.get('per_chg'),
                'volume': item.get('volume')
            })

        # Prepare payload for GAS WebApp
        post = {
            'action': 'chartink_import',
            'payload': {
                'stocks': stocks,
                'scanner_name': os.getenv('SCANNER_NAME','Rocket Rajan Scanner'),
                'scanner_url': os.getenv('SCANNER_URL',''),
                'detected_count': len(stocks)
            }
        }

        # Forward to GAS WebApp
        if WEBAPP_EXEC_URL:
            try:
                resp = requests.post(WEBAPP_EXEC_URL, json=post, timeout=20)
                send_telegram(f'📥 Chartink alert processed — forwarded to WebApp. Detected: {len(stocks)}')
            except Exception as e:
                send_telegram('❌ Failed to forward to WebApp: '+str(e))
        else:
            send_telegram('❗ WEBAPP_EXEC_URL not configured in environment')

        return jsonify({'ok':True, 'detected': len(stocks)})
    except Exception as e:
        send_telegram('❌ Render webhook error: '+str(e))
        return jsonify({'ok':False,'error':str(e)}),500

@app.route('/health')
def health():
    return jsonify({'ok':True,'ts':int(time.time())})

if __name__ == '__main__':
    port = int(os.getenv('PORT', '10000'))
    app.run(host='0.0.0.0', port=port)
