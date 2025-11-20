# main.py
# RajanTradeAutomation - Render webhook + FYERS integration (symbolUpdate-capable)
# Replace your existing main.py with this file. This preserves your Chartink -> WebApp flow,
# and only adds FYERS for live ticks & volume.

from flask import Flask, request, jsonify
import os, requests, time, traceback, json, threading, queue

app = Flask(__name__)

# ------------------- Existing env vars -------------------
WEBAPP_EXEC_URL = os.getenv("WEBAPP_EXEC_URL")  # Google Apps Script exec URL
CHARTINK_TOKEN  = os.getenv("CHARTINK_TOKEN", "RAJAN123")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
INTERVAL_SECS   = int(os.getenv("INTERVAL_SECS", "1800"))
TEST_TOKEN      = os.getenv("TEST_TOKEN", "TEST123")
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

# ------------------- FYERS env vars -------------------
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")
FYERS_TOKEN_FILE = os.getenv("FYERS_TOKEN_FILE", "fyers_token.json")

# ------------------- FYERS tuning -------------------
FYERS_WS_URL_TEMPLATE = "wss://api.fyers.in/socket/v2/dataSock?access_token={token}"
FYERS_SUB_BATCH = int(os.getenv("FYERS_SUB_BATCH", "25"))
FYERS_RECONNECT_BACKOFF = int(os.getenv("FYERS_RECONNECT_BACKOFF", "3"))

# ------------------- imports -------------------
try:
    from fyers_apiv3 import fyersModel
except:
    fyersModel = None

try:
    import websocket
except:
    websocket = None

# ------------------- Telegram helper -------------------
def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text})
    except:
        pass

# ------------------- Google Script POST helper -------------------
def gs_post(payload: dict):
    if not WEBAPP_EXEC_URL:
        raise Exception("WEBAPP_EXEC_URL not configured")
    r = requests.post(WEBAPP_EXEC_URL, json=payload)
    try:
        return r.json()
    except:
        return {"ok": False, "raw": r.text}

# ------------------- Existing NSE/Yahoo quote engines -------------------
def fetch_nse_quote(symbol):
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com/"
        }
        url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
        s = requests.Session()
        s.headers.update(headers)
        _ = s.get("https://www.nseindia.com")
        r = s.get(url)
        if r.status_code == 200:
            j = r.json()
            p = j["priceInfo"]
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
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}.NS"
        r = requests.get(url, headers={"User-Agent": USER_AGENT})
        q = r.json()["quoteResponse"]["result"]
        if q:
            rec = q[0]
            return {
                "price": rec.get("regularMarketPrice"),
                "changePercent": rec.get("regularMarketChangePercent"),
                "volume": rec.get("regularMarketVolume")
            }
    except:
        pass
    return None

# ------------------- FYERS token persistence -------------------
def save_fyers_tokens(data):
    try:
        with open(FYERS_TOKEN_FILE, "w") as f:
            json.dump(data, f)
        os.environ["FYERS_ACCESS_TOKEN"] = data.get("access_token","")
        return True
    except:
        return False

def load_fyers_tokens():
    try:
        if os.path.exists(FYERS_TOKEN_FILE):
            return json.load(open(FYERS_TOKEN_FILE))
    except:
        pass
    return {}

# ------------------- In-memory FYERS tick store -------------------
fyers_ticks = {}
fyers_ticks_lock = threading.Lock()
subscription_queue = queue.Queue()

ws_app_instance = {"obj": None, "lock": threading.Lock()}
ws_thread = {"obj": None, "running": False}

# ------------------- Utility -------------------
def to_fyers_instrument(sym):
    s = sym.strip().upper()
    if ":" in s:
        return s
    return f"NSE:{s}-EQ"

# ------------------- FYERS WebSocket handlers -------------------
def on_fyers_open(ws):
    print("FYERS WS opened")
    batch = []
    while not subscription_queue.empty():
        batch.append(subscription_queue.get())
        if len(batch) >= FYERS_SUB_BATCH:
            ws.send(json.dumps({"type": "subscribe","payload":{"symbols": batch}}))
            print("Subscribed batch:", batch)
            batch = []
    if batch:
        ws.send(json.dumps({"type": "subscribe","payload":{"symbols": batch}}))
        print("Subscribed final batch:", batch)

def on_fyers_message(ws, message):
    try:
        data = json.loads(message)
    except:
        print("Raw:", message)
        return
    with fyers_ticks_lock:
        if "d" in data:
            for entry in data["d"]:
                sym = entry.get("s")
                if sym:
                    fyers_ticks[sym] = entry

def on_fyers_close(ws, code, reason):
    print("FYERS WS closed")
    ws_thread["running"] = False
    time.sleep(FYERS_RECONNECT_BACKOFF)
    start_fyers_ws_background()

def on_fyers_error(ws, err):
    print("FYERS WS error:", err)

# ------------------- Start WS -------------------
def start_fyers_ws_background():
    if ws_thread["running"]:
        return
    tokens = load_fyers_tokens()
    access_token = tokens.get("access_token")
    if not access_token:
        print("No FYERS token")
        return
    ws_url = FYERS_WS_URL_TEMPLATE.format(token=access_token)

    def run():
        ws_thread["running"] = True
        while ws_thread["running"]:
            try:
                ws = websocket.WebSocketApp(
                    ws_url,
                    on_open=on_fyers_open,
                    on_message=on_fyers_message,
                    on_close=on_fyers_close,
                    on_error=on_fyers_error
                )
                ws_app_instance["obj"] = ws
                ws.run_forever()
            except:
                pass
            time.sleep(FYERS_RECONNECT_BACKOFF)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    ws_thread["obj"] = t
    print("WS thread started")

# ------------------- Subscribe helper -------------------
def queue_subscribe_symbols(symbols):
    for s in symbols:
        subscription_queue.put(to_fyers_instrument(s))

# ------------------- FYERS quote reader -------------------
def fetch_fyers_quote(symbol):
    key = to_fyers_instrument(symbol)
    with fyers_ticks_lock:
        if key in fyers_ticks:
            e = fyers_ticks[key]
            return {
                "price": e.get("ltp"),
                "changePercent": e.get("ch"),
                "volume": e.get("vol")
            }
    return None

# ------------------- get_quote -------------------
def get_quote(symbol):
    out = fetch_fyers_quote(symbol)
    if out and out["price"]:
        return out
    out = fetch_nse_quote(symbol)
    if out and out["price"]:
        return out
    out = fetch_yahoo_quote(symbol)
    return out or {"price": None, "changePercent": None, "volume": None}

# ------------------- FYERS Auth -------------------
@app.get("/fyers-auth")
def fyers_auth():
    if not (FYERS_CLIENT_ID and FYERS_SECRET_KEY and FYERS_REDIRECT_URI):
        return jsonify({"ok":False,"error":"Missing config"})
    state = "rajan_state"
    try:
        session = fyersModel.SessionModel(
            client_id=FYERS_CLIENT_ID,
            secret_key=FYERS_SECRET_KEY,
            redirect_uri=FYERS_REDIRECT_URI,
            response_type="code",
            state=state
        )
        auth_url = session.generate_authcode()
    except:
        # NEW FIXED URL
        import urllib.parse
        auth_url = (
            "https://api-t1.fyers.in/api/v3/generate-authcode?"
            f"client_id={FYERS_CLIENT_ID}&redirect_uri={urllib.parse.quote(FYERS_REDIRECT_URI)}"
            f"&response_type=code&state={state}"
        )
    return jsonify({"ok":True,"auth_url":auth_url})

@app.get("/fyers-redirect")
def fyers_redirect():
    try:
        auth_code = request.args.get("code")
        if not auth_code:
            return "Missing code", 400

        session = fyersModel.SessionModel(
            client_id=FYERS_CLIENT_ID,
            secret_key=FYERS_SECRET_KEY,
            redirect_uri=FYERS_REDIRECT_URI,
            response_type="code",
            grant_type="authorization_code"
        )
        session.set_token(auth_code)
        token_response = session.generate_token()
        save_fyers_tokens(token_response)
        start_fyers_ws_background()
        send_telegram("FYERS token saved. WS starting.")
        return "Auth successful — token saved and WS starting."
    except Exception as e:
        send_telegram(f"FYERS redirect error: {e}")
        return str(e), 500

# ------------------- Chartink webhook -------------------
@app.post("/chartink-alert")
def chartink_alert():
    try:
        token = request.args.get("token")
        if CHARTINK_TOKEN and token and token != CHARTINK_TOKEN:
            return jsonify({"ok":False,"error":"Invalid token"}),403

        data = request.get_json(force=True) or {}
        stocks = data.get("stocks") or data.get("symbols") or []
        if isinstance(stocks, str):
            stocks = stocks.split(",")

        stocks = [s.strip().upper() for s in stocks if s.strip()]

        if not stocks:
            gs_post({"action":"chartink_import","payload":{"stocks":[]}})
            return jsonify({"ok":True})

        # Sub to FYERS
        queue_subscribe_symbols(stocks)

        enriched=[]
        for sym in stocks:
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
        return jsonify({"ok":True,"webapp":res})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}),500

@app.get("/health")
def health():
    return jsonify({"ok":True})

if __name__ == "__main__":
    print("Starting Service")
    try:
        tokens = load_fyers_tokens()
        if tokens.get("access_token"):
            start_fyers_ws_background()
    except:
        pass
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","10000")))
