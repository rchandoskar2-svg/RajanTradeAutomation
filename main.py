# main.py
# RajanTradeAutomation - Render webhook + FYERS integration (symbolUpdate-capable)
# Replace your existing main.py with this file. This preserves your Chartink -> WebApp flow,
# and only adds FYERS for live ticks & volume. Do not modify other Apps Script files.

from flask import Flask, request, jsonify
import os, requests, time, traceback, json, threading, queue

app = Flask(__name__)

# ------------------- Existing env vars (already present) -------------------
WEBAPP_EXEC_URL = os.getenv("WEBAPP_EXEC_URL")  # Google Apps Script exec URL
CHARTINK_TOKEN  = os.getenv("CHARTINK_TOKEN", "RAJAN123")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
INTERVAL_SECS   = int(os.getenv("INTERVAL_SECS", "1800"))
TEST_TOKEN      = os.getenv("TEST_TOKEN", "TEST123")
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

# ------------------- FYERS env vars (you added) -------------------
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
FYERS_SECRET_KEY = os.getenv("FYERS_SECRET_KEY")
FYERS_REDIRECT_URI = os.getenv("FYERS_REDIRECT_URI")
FYERS_TOKEN_FILE = os.getenv("FYERS_TOKEN_FILE", "fyers_token.json")  # persisted token file

# ------------------- Optional tuning -------------------
FYERS_WS_URL_TEMPLATE = "wss://api.fyers.in/socket/v2/dataSock?access_token={token}"
FYERS_SUB_BATCH = int(os.getenv("FYERS_SUB_BATCH", "25"))  # subscribe in batches to avoid bursts
FYERS_RECONNECT_BACKOFF = int(os.getenv("FYERS_RECONNECT_BACKOFF", "3"))

# ------------------- imports for FYERS -------------------
try:
    from fyers_apiv3 import fyersModel
except Exception:
    fyersModel = None

try:
    import websocket
except Exception:
    websocket = None

# ------------------- Telegram helper -------------------
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

# ------------------- Google Script POST helper -------------------
def gs_post(payload: dict):
    if not WEBAPP_EXEC_URL:
        raise Exception("WEBAPP_EXEC_URL not configured")
    r = requests.post(WEBAPP_EXEC_URL, json=payload, timeout=30)
    try:
        return r.json()
    except:
        return {"ok": False, "raw": r.text}

# ------------------- Existing quote engines (unchanged) -------------------
def fetch_nse_quote(symbol):
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/"
        }
        url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
        s = requests.Session()
        s.headers.update(headers)
        _ = s.get("https://www.nseindia.com", timeout=10)
        r = s.get(url, timeout=10)
        if r.status_code == 200:
            j = r.json()
            if "priceInfo" in j and j["priceInfo"]:
                p = j["priceInfo"]
                return {
                    "price": p.get("lastPrice"),
                    "changePercent": p.get("pChange"),
                    "volume": p.get("totalTradedVolume"),
                    "open": p.get("open"),
                    "high": p.get("intraDayHigh"),
                    "low": p.get("intraDayLow"),
                    "prevClose": p.get("previousClose")
                }
    except Exception as e:
        print("NSE fetch error for", symbol, e)
    return None

def fetch_yahoo_quote(symbol):
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
                    "volume": rec.get("regularMarketVolume"),
                    "open": rec.get("regularMarketOpen"),
                    "high": rec.get("regularMarketDayHigh"),
                    "low": rec.get("regularMarketDayLow"),
                    "prevClose": rec.get("regularMarketPreviousClose")
                }
    except Exception as e:
        print("Yahoo fetch error", symbol, e)
    return None

# ------------------- FYERS token persistence -------------------
def save_fyers_tokens(data):
    try:
        with open(FYERS_TOKEN_FILE, "w") as f:
            json.dump(data, f)
        os.environ["FYERS_ACCESS_TOKEN"] = data.get("access_token","")
        return True
    except Exception as e:
        print("save_fyers_tokens error:", e)
        return False

def load_fyers_tokens():
    try:
        if os.path.exists(FYERS_TOKEN_FILE):
            with open(FYERS_TOKEN_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        print("load_fyers_tokens error:", e)
    return {}

# ------------------- In-memory FYERS ticks cache and subscription queue -------------------
fyers_ticks = {}       # key -> latest tick dict
fyers_ticks_lock = threading.Lock()
subscription_queue = queue.Queue()
ws_app_instance = {"obj": None, "lock": threading.Lock()}
ws_thread = {"obj": None, "running": False}

# ------------------- Utility: convert plain symbol to FYERS instrument -------------------
def to_fyers_instrument(sym):
    # assume NSE equity - convert to "NSE:SYMBOL-EQ"
    s = sym.strip().upper()
    if ":" in s or "-EQ" in s:
        return s
    return f"NSE:{s}-EQ"

# ------------------- FYERS WebSocket handlers -------------------
def on_fyers_open(ws):
    print("FYERS WS opened")
    # process initial subscribe queue in batches
    try:
        # consume queue into batch list
        batch = []
        while not subscription_queue.empty():
            batch.append(subscription_queue.get_nowait())
            if len(batch) >= FYERS_SUB_BATCH:
                msg = {"type": "subscribe", "payload": {"symbols": batch}}
                ws.send(json.dumps(msg))
                print("Subscribed batch:", batch)
                batch = []
        if batch:
            msg = {"type": "subscribe", "payload": {"symbols": batch}}
            ws.send(json.dumps(msg))
            print("Subscribed final batch:", batch)
    except Exception as e:
        print("on_fyers_open subscribe error:", e)

def on_fyers_message(ws, message):
    # FYERS can send JSON payloads — parse and update fyers_ticks
    try:
        data = json.loads(message)
    except Exception:
        # sometimes raw text
        print("FYERS WS raw message (non-json):", message)
        return

    # Parse common shapes: 'd' array or single symbol update
    try:
        with fyers_ticks_lock:
            if isinstance(data, dict):
                # example: {"d":[{...}, {...}], "t":...}
                if "d" in data and isinstance(data["d"], list):
                    for entry in data["d"]:
                        # entry may contain instrument/symbol keys
                        sym = entry.get("s") or entry.get("symbol") or entry.get("instrument")
                        if not sym:
                            # try instrument code mapping fields
                            sym = entry.get("symbol_id") or entry.get("i")
                        if sym:
                            fyers_ticks[str(sym)] = entry
                elif data.get("symbol"):
                    fyers_ticks[data["symbol"]] = data
                else:
                    # pragmatic: if keys look like a tick
                    for k,v in data.items():
                        # skip meta
                        if k in ("t","v","status"): continue
                    # store entire dict with timestamp
                    fyers_ticks[str(time.time())] = data
    except Exception as e:
        print("on_fyers_message parse error:", e)

def on_fyers_close(ws, code, reason):
    print("FYERS WS closed:", code, reason)
    ws_thread["running"] = False
    # auto-reconnect with backoff
    time.sleep(FYERS_RECONNECT_BACKOFF)
    start_fyers_ws_background()

def on_fyers_error(ws, err):
    print("FYERS WS error:", err)

# ------------------- Start / manage WS background thread -------------------
def start_fyers_ws_background():
    # spawn a background thread that connects to fyers ws and keeps it open
    if ws_thread["running"]:
        print("FYERS WS already running")
        return

    tokens = load_fyers_tokens()
    access_token = tokens.get("access_token") or os.getenv("FYERS_ACCESS_TOKEN")
    if not access_token:
        print("No FYERS access token available; cannot start WS")
        return

    ws_url = FYERS_WS_URL_TEMPLATE.format(token=access_token)

    def run():
        ws_thread["running"] = True
        while ws_thread["running"]:
            try:
                if websocket is None:
                    print("websocket-client not installed")
                    return
                ws = websocket.WebSocketApp(
                    ws_url,
                    on_open=on_fyers_open,
                    on_message=on_fyers_message,
                    on_close=on_fyers_close,
                    on_error=on_fyers_error
                )
                with ws_app_instance["lock"]:
                    ws_app_instance["obj"] = ws
                ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                print("FYERS WS loop error:", e)
            time.sleep(FYERS_RECONNECT_BACKOFF)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    ws_thread["obj"] = t
    print("FYERS websocket background thread started.")

# ------------------- Subscribe helper (places instruments into queue) -------------------
def queue_subscribe_symbols(symbols):
    # Convert to fyers instrument format, dedupe, push to queue
    instruments = [to_fyers_instrument(s) for s in symbols]
    # dedupe
    seen = set()
    insts = []
    for i in instruments:
        if i not in seen:
            seen.add(i)
            insts.append(i)
    for inst in insts:
        subscription_queue.put(inst)
    # if ws open, trigger immediate subscribe by sending a small ping to open handler
    with ws_app_instance["lock"]:
        ws = ws_app_instance["obj"]
        try:
            if ws and hasattr(ws, "send"):
                # send ping to process queue (on_open handles batch subscribe; here we just attempt to flush)
                pass
        except Exception:
            pass

# ------------------- fetch_fyers_quote (reads in-memory cache) -------------------
def fetch_fyers_quote(symbol):
    # try multiple key variants to find match
    keys_to_try = [symbol, to_fyers_instrument(symbol), f"NSE:{symbol}-EQ", f"{symbol}-EQ"]
    with fyers_ticks_lock:
        for k in keys_to_try:
            if k in fyers_ticks:
                entry = fyers_ticks[k]
                # normalize common fields, tolerant to variants
                price = entry.get("ltp") or entry.get("lastPrice") or entry.get("price") or entry.get("l")
                vol = entry.get("volume") or entry.get("v") or entry.get("vol") or entry.get("totalTradedVolume")
                chg = entry.get("changePercent") or entry.get("pChange") or entry.get("pc")
                low = entry.get("low") or entry.get("intraDayLow") or entry.get("lowl")
                high = entry.get("high") or entry.get("intraDayHigh") or entry.get("h")
                prev = entry.get("prevClose") or entry.get("previousClose") or entry.get("pc")
                # some feeds include last traded qty / turnover
                ltq = entry.get("lastTradedQty") or entry.get("ltq") or entry.get("lq")
                return {
                    "price": price,
                    "changePercent": chg,
                    "volume": vol,
                    "low": low,
                    "high": high,
                    "prevClose": prev,
                    "last_traded_qty": ltq,
                    "raw": entry
                }
    return None

# ------------------- get_quote (priority: FYERS -> NSE -> Yahoo) -------------------
def get_quote(symbol):
    # 1) try fyers cache
    out = fetch_fyers_quote(symbol)
    if out and out.get("price") is not None:
        return out
    # 2) original flows
    out = fetch_nse_quote(symbol)
    if out and out.get("price") is not None:
        return out
    out = fetch_yahoo_quote(symbol)
    return out or {"price": None, "changePercent": None, "volume": None}

# ------------------- FYERS Auth endpoints -------------------
@app.get("/fyers-auth")
def fyers_auth():
    try:
        if not FYERS_CLIENT_ID or not FYERS_SECRET_KEY or not FYERS_REDIRECT_URI:
            return jsonify({"ok": False, "error": "FYERS_CLIENT_ID / SECRET / REDIRECT not configured"}), 400
        response_type = "code"
        state = "rajan_state"
        try:
            session = fyersModel.SessionModel(
                client_id=FYERS_CLIENT_ID,
                secret_key=FYERS_SECRET_KEY,
                redirect_uri=FYERS_REDIRECT_URI,
                response_type=response_type,
                state=state
            )
            auth_url = session.generate_authcode()
        except Exception:
            auth_url = (
                "https://api.fyers.in/api/v3/generate-authcode?"
                f"client_id={FYERS_CLIENT_ID}&redirect_uri={requests.utils.quote(FYERS_REDIRECT_URI)}&response_type=code&state={state}"
            )
        return jsonify({"ok": True, "auth_url": auth_url}), 200
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.get("/fyers-redirect")
def fyers_redirect():
    try:
        auth_code = request.args.get("code") or request.args.get("auth_code") or request.args.get("authcode")
        if not auth_code:
            return "Missing auth code", 400
        if not fyersModel:
            return "fyers_apiv3 package not installed on server", 500
        session = fyersModel.SessionModel(
            client_id=FYERS_CLIENT_ID,
            secret_key=FYERS_SECRET_KEY,
            redirect_uri=FYERS_REDIRECT_URI,
            response_type="code",
            grant_type="authorization_code"
        )
        session.set_token(auth_code)
        token_response = session.generate_token()
        # persist tokens
        save_fyers_tokens(token_response)
        # start websocket
        start_fyers_ws_background()
        try:
            send_telegram("✅ FYERS access token generated and saved. WebSocket starting.")
        except:
            pass
        return "Auth successful — token saved and WS starting.", 200
    except Exception as e:
        tb = traceback.format_exc()
        print("fyers_redirect error", tb)
        try:
            send_telegram(f"❌ FYERS token exchange error: {e}")
        except:
            pass
        return f"Error exchanging auth code: {e}", 500

# Optional token refresh helper (callable via internal cron)
def refresh_fyers_token_if_needed():
    try:
        tokens = load_fyers_tokens()
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            return False
        session = fyersModel.SessionModel(
            client_id=FYERS_CLIENT_ID,
            secret_key=FYERS_SECRET_KEY,
            redirect_uri=FYERS_REDIRECT_URI,
            response_type="code",
            grant_type="refresh_token"
        )
        session.set_token(refresh_token)
        resp = session.generate_token()
        if resp and resp.get("access_token"):
            save_fyers_tokens(resp)
            return True
    except Exception as e:
        print("refresh_fyers_token_if_needed error", e)
    return False

# ------------------- Chartink webhook route (keeps your original behaviour) -------------------
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

        # Queue subscription for FYERS (so WS will start streaming these instruments)
        queue_subscribe_symbols(symbols)

        # fetch quotes (prefer fyers cache)
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

# ------------------- Run server -------------------
if __name__ == "__main__":
    print("Starting RajanTradeAutomation Render Service with FYERS integration...")
    # try start WS if token present
    try:
        tokens = load_fyers_tokens()
        if tokens.get("access_token"):
            start_fyers_ws_background()
    except Exception as e:
        print("Error starting fyers ws at boot:", e)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
