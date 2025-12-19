# ============================================================
# RajanTradeAutomation – main.py
# VERSION: v3.2 FINAL
# WS DEADLOCK FIX + TIME WINDOW SHIFT
# ============================================================

import os, time, threading
from datetime import datetime
from flask import Flask, jsonify, request

# ------------------------------------------------------------
# NSE CLIENT
# ------------------------------------------------------------
try:
    from nsetools import Nse
    NSE_CLIENT = Nse()
except Exception:
    NSE_CLIENT = None
    print("❌ NSE CLIENT INIT FAILED")

# ------------------------------------------------------------
# ENV
# ------------------------------------------------------------
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

if not FYERS_ACCESS_TOKEN:
    raise Exception("❌ FYERS_ACCESS_TOKEN missing")

# ------------------------------------------------------------
# ALL SYMBOLS (FULL UNIVERSE)
# ------------------------------------------------------------
ALL_SYMBOLS = [
    "NSE:SBIN-EQ",
    "NSE:RELIANCE-EQ",
    "NSE:VEDL-EQ",
    "NSE:AXISBANK-EQ",
    "NSE:KOTAKBANK-EQ",
    # ⬇️ इथे तुझी पूर्ण 160–170 stocks list ठेव
]

# ------------------------------------------------------------
# FLASK ROUTES (LOCKED)
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "RajanTradeAutomation"})

@app.route("/callback")
def fyers_callback():
    return jsonify({"status": "callback_received"})

@app.route("/fyers-redirect")
def fyers_redirect():
    return jsonify({
        "status": "auth_code_received",
        "auth_code": request.args.get("auth_code"),
        "state": request.args.get("state")
    })

# ------------------------------------------------------------
# FYERS WS
# ------------------------------------------------------------
from fyers_apiv3.FyersWebsocket import data_ws

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
TF_SECS = 300
MAX_TRADES = 5

# TEST WINDOW BASE (TODAY ONLY)
TEST_START_HOUR = 10
TEST_START_MIN = 0   # 10:00

# ------------------------------------------------------------
# STATE
# ------------------------------------------------------------
candles_L1 = {}
bucket_L1 = {}

candles_L2 = {}
bucket_L2 = {}

selected_stocks = set()
signal_book = {}

bias_done = False
bias_side = None
l2_ready = False
executed_trades = 0

# ------------------------------------------------------------
# TIME HELPERS
# ------------------------------------------------------------
def bucket_ts(ts):
    return ts - (ts % TF_SECS)

def tstr(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M")

def in_test_window():
    now = datetime.now()
    start = now.replace(hour=TEST_START_HOUR, minute=TEST_START_MIN, second=0)
    return now >= start

# ------------------------------------------------------------
# REAL BIAS + SECTOR LOGIC
# ------------------------------------------------------------
def get_nifty50_breadth():
    q = NSE_CLIENT.get_index_quote("NIFTY 50")
    return int(q.get("advances",0)), int(q.get("declines",0))

def compute_bias(a, d):
    return "BUY" if a > d else "SELL"

def fetch_sectors():
    idx = NSE_CLIENT.get_all_index_quote()
    return sorted(
        [i for i in idx if i.get("index","").startswith("NIFTY")],
        key=lambda x: float(x.get("percentChange",0)),
        reverse=True
    )

def select_top2_sectors(bias):
    s = fetch_sectors()
    return [x["index"] for x in (s[:2] if bias=="BUY" else s[-2:])]

def fetch_stocks(sectors, bias):
    out = set()
    for sec in sectors:
        rows = NSE_CLIENT.get_stock_quote_in_index(index=sec, include_index=False)
        for r in rows:
            pchg = float(r.get("pChange",0))
            sym = r.get("symbol")
            if not sym:
                continue
            if bias=="BUY" and 0 < pchg <= 2.5:
                out.add(f"NSE:{sym}-EQ")
            if bias=="SELL" and 0 > pchg >= -2.5:
                out.add(f"NSE:{sym}-EQ")
    return out

# ------------------------------------------------------------
# BIAS SWITCH (ONCE)
# ------------------------------------------------------------
def try_bias_switch():
    global bias_done, bias_side, selected_stocks, l2_ready

    if bias_done or not in_test_window():
        return

    now = datetime.now().strftime("%H:%M:%S")
    if "10:10:10" <= now <= "10:12:00":
        adv, dec = get_nifty50_breadth()
        bias_side = compute_bias(adv, dec)
        sectors = select_top2_sectors(bias_side)
        selected_stocks = fetch_stocks(sectors, bias_side)

        bias_done = True
        print(f"[BIAS] {bias_side} ADV={adv} DEC={dec}")
        print(f"[L2 STOCKS] {len(selected_stocks)}")

        for s in selected_stocks:
            if s in candles_L1:
                candles_L2[s] = dict(list(candles_L1[s].items())[:3])

        l2_ready = True
        print("[L2 READY]")

# ------------------------------------------------------------
# SIGNAL + ENTRY
# ------------------------------------------------------------
def check_signal(sym, c):
    vols = [x["vol"] for x in candles_L2[sym].values()]
    if c["vol"] != min(vols):
        return

    if bias_side=="BUY" and c["open"] > c["close"]:
        signal_book[sym] = ("BUY", c["high"], c["low"])
        print(f"[SIGNAL BUY] {sym}")

    if bias_side=="SELL" and c["close"] > c["open"]:
        signal_book[sym] = ("SELL", c["high"], c["low"])
        print(f"[SIGNAL SELL] {sym}")

def try_entry(sym, ltp):
    global executed_trades
    if sym not in signal_book or executed_trades >= MAX_TRADES:
        return

    side, hi, lo = signal_book[sym]
    if side=="BUY" and ltp > hi:
        executed_trades += 1
        print(f"[ENTRY BUY] {sym} {executed_trades}/{MAX_TRADES}")
        signal_book.pop(sym)

    if side=="SELL" and ltp < lo:
        executed_trades += 1
        print(f"[ENTRY SELL] {sym} {executed_trades}/{MAX_TRADES}")
        signal_book.pop(sym)

# ------------------------------------------------------------
# WS CALLBACKS
# ------------------------------------------------------------
def on_message(msg):
    sym = msg.get("symbol")
    ltp = msg.get("ltp")
    ts = msg.get("exch_feed_time")
    vol = msg.get("last_traded_qty",0)

    if not sym or not ltp or not ts:
        return

    b = bucket_ts(ts)

    candles_L1.setdefault(sym,{})
    if bucket_L1.get(sym) != b:
        if sym in bucket_L1:
            c = candles_L1[sym][bucket_L1[sym]]
            print(f"[L1] {sym} {tstr(bucket_L1[sym])} O:{c['open']} C:{c['close']} V:{c['vol']}")
        candles_L1[sym][b] = {"open":ltp,"high":ltp,"low":ltp,"close":ltp,"vol":vol}
        bucket_L1[sym] = b
    else:
        c = candles_L1[sym][b]
        c["high"] = max(c["high"], ltp)
        c["low"] = min(c["low"], ltp)
        c["close"] = ltp
        c["vol"] += vol

    try_bias_switch()

    if l2_ready and sym in selected_stocks:
        candles_L2.setdefault(sym,{})
        if bucket_L2.get(sym) != b:
            if sym in bucket_L2:
                check_signal(sym, candles_L2[sym][bucket_L2[sym]])
            candles_L2[sym][b] = {"open":ltp,"high":ltp,"low":ltp,"close":ltp,"vol":vol}
            bucket_L2[sym] = b
        else:
            c2 = candles_L2[sym][b]
            c2["high"] = max(c2["high"], ltp)
            c2["low"] = min(c2["low"], ltp)
            c2["close"] = ltp
            c2["vol"] += vol

        try_entry(sym, ltp)

def on_connect():
    print("🔗 WS CONNECTED")
    fyers_ws.subscribe(symbols=ALL_SYMBOLS, data_type="SymbolUpdate")

def on_error(e): print("WS ERROR", e)
def on_close(e): print("WS CLOSED", e)

# ------------------------------------------------------------
# START WS
# ------------------------------------------------------------
def start_ws():
    global fyers_ws
    fyers_ws = data_ws.FyersDataSocket(
        access_token=FYERS_ACCESS_TOKEN,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_connect=on_connect,
        reconnect=True
    )
    fyers_ws.connect()

threading.Thread(target=start_ws, daemon=True).start()

# ------------------------------------------------------------
# FLASK RUN
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
