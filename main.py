# Main.py - minimal robust Chartink -> GAS forwarder (use with Render)
from flask import Flask, request, jsonify
import os, requests, time

app = Flask(__name__)

WEBAPP_EXEC_URL = os.getenv('WEBAPP_EXEC_URL')
CHARTINK_TOKEN = os.getenv('CHARTINK_TOKEN','RAJAN123')
HEADERS = {'User-Agent':'Mozilla/5.0','Content-Type':'application/json'}

@app.route('/chartink-alert', methods=['POST'])
def chartink_alert():
    try:
        token = request.args.get('token','')
        if CHARTINK_TOKEN and token != CHARTINK_TOKEN:
            return jsonify({'ok':False,'error':'invalid token'}), 403

        # incoming might be from Chartink webhook (but we will call process to enrich)
        incoming = request.get_json(force=True, silent=True) or {}

        # call chartink process endpoint (same as F12)
        payload = {'scan_clause': os.getenv('SCAN_CLAUSE','( {33492} ( [0] 1 minute close < [0] 1 minute open ) )'), 'debug_clause': ''}
        try:
            r = requests.post('https://chartink.com/screener/process', json=payload, headers=HEADERS, timeout=12)
            j = r.json() if r.status_code==200 else {}
        except Exception as e:
            j = {}

        # build stocks list robustly
        stocks = []
        for item in j.get('data', []):
            sym = item.get('nsecode') or item.get('symbol')
            if not sym: continue
            stocks.append({
                'nsecode': sym,
                'close': item.get('close'),
                'per_chg': item.get('per_chg'),
                'volume': item.get('volume')
            })

        # forward to GAS WebApp as payload.payload (WebApp expects payload.payload or payload)
        post = {
            'action': 'chartink_import',
            'payload': {
                'stocks': stocks,
                'scanner_name': os.getenv('SCANNER_NAME','Rocket Rajan Scanner'),
                'scanner_url': os.getenv('SCANNER_URL',''),
                'detected_count': len(stocks),
                'incoming_preview': str(incoming)[:400]
            }
        }

        if WEBAPP_EXEC_URL:
            try:
                resp = requests.post(WEBAPP_EXEC_URL, json=post, timeout=15)
            except Exception as e:
                pass

        return jsonify({'ok':True,'detected':len(stocks)})
    except Exception as e:
        return jsonify({'ok':False,'error':str(e)}),500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '10000')))
