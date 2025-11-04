from flask import Flask, request, jsonify
import os, json, requests, time

app = Flask(__name__)
APP_NAME = "RajanTradeAutomation"

WEBAPP_EXEC_URL = os.getenv("WEBAPP_EXEC_URL")

def gs_post(payload):
    r = requests.post(WEBAPP_EXEC_URL, json=payload, timeout=20)
    r.raise_for_status()
    return r.json()

@app.get("/health")
def health():
    return jsonify({"ok":True,"app":APP_NAME,"ts":int(time.time())})

@app.post("/chartink-alert")
def chartink_alert():
    try:
        data = request.get_json(force=True, silent=True) or {}
        res = gs_post({"action":"chartink_import","payload":data})
        return jsonify({"ok":True,"sheet":res})
    except Exception as e:
        try:
            gs_post({"action":"phase22_error","message":str(e)})
        except:
            pass
        return jsonify({"ok":False,"error":str(e)}),500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
