# ============================================================
# RajanTradeAutomation – main.py
# VERSION: v3 FINAL
# Live WS + Candle + REAL Bias/Sector + Entry Engine
# ============================================================

import os, time, threading
from datetime import datetime
from flask import Flask, jsonify, request

# ------------------------------------------------------------
# NSE CLIENT (REAL)
# ------------------------------------------------------------
try:
    from nsetools import Nse
    NSE_CLIENT = Nse()
except Exception:
    NSE_CLIENT = None

# ------------------------------------------------------------
# ENV
# ------------------------------------------------------------
FYERS_CLIENT_ID = os.getenv("FYERS_CLIENT_ID")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

if not FYERS_CLIENT_ID or not FYERS_ACCESS_TOKEN:
    raise Exception("FYERS ENV missing")

# ------------------------------------------------------------
# FLASK (DO NOT TOUCH)
# ------------------------------------------------------------
app = Flask(__name__)

@app.route("/")
def health():
    return jsonify({"status": "ok", "service": "RajanTradeAutomation"})

@app.route("/callback")
def fyers_callback():
    auth_code = request.args.get("auth_code")
    print("🔑 FYERS CALLBACK:", auth_code)
    return jsonify({"status": "callback_received", "auth_code": auth_code})

# ------------------------------------------------------------
# FYERS WS
# ------------------------------------------------------------
from fyers_apiv3.FyersWebsocket import data_ws

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
TF_SECS = 300
MAX_TRADES = 5

# ------------------------------------------------------------
# FLAGS
# ------------------------------------------------------------
bias_done = False
bias_side = None
l2_ready = False
trading_active = False
executed_trades = 0

# ------------------------------------------------------------
# DATA STRUCTURES
# ------------------------------------------------------------
candles_L1 = {}
bucket_L1 = {}

candles_L2 = {}
bucket_L2 = {}

selected_stocks = set()
signal_book = {}

# ------------------------------------------------------------
# TIME HELPERS
# ------------------------------------------------------------
def bucket_ts(ts):
    return ts - (ts % TF_SECS)

def tstr(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M")

# ------------------------------------------------------------
# REAL BIAS LOGIC (FROM OLD CODE)
# ------------------------------------------------------------
def get_nifty50_breadth():
    q = NSE_CLIENT.get_index_quote("NIFTY 50")
    return int(q.get("advances",0)), int(q.get("declines",0))

def compute_bias(adv, dec):
    return "BUY" if adv > dec else "SELL"

def fetch_sector_perf():
    all_idx = NSE_CLIENT.get_all_index_quote()
    sectors = []
    for i in all_idx:
        name = i.get("index")
        if not name or not name.startswith("NIFTY"):
            continue
        sectors.append({
            "name": name,
            "chg": float(i.get("percentChange",0))
        })
    return sectors

def select_top2_sectors(bias):
    s = fetch_sector_perf()
    s = sorted(s, key=lambda x: x["chg"], reverse=(bias=="BUY"))
    return [x["name"] for x in s[:2]]

def fetch_stocks_from_sectors(sectors, bias):
    stocks = set()
    for sec in sectors:
        rows = NSE_CLIENT.get_stock_quote_in_index(index=sec, include_index=False)
        for r in rows:
            pchg = float(r.get("pChange",0))
            sym = r.get("symbol")
            if not sym:
                continue
            if bias=="BUY" and 0 < pchg <= 2.5:
                stocks.add(f"NSE:{sym}-EQ")
            if bias=="SELL" and 0 > pchg >= -2.5:
                stocks.add(f"NSE:{sym}-EQ")
    return stocks

# ------------------------------------------------------------
# BIAS WINDOW (ONE TIME)
# ------------------------------------------------------------
def try_bias_switch():
    global bias_done, bias_side, selected_stocks, trading_active, l2_ready

    if bias_done:
        return

    now = datetime.now().strftime("%H:%M:%S")
    if "09:25:10" <= now <= "09:27:00":
        adv, dec = get_nifty50_breadth()
        bias_side = compute_bias(adv, dec)

        sectors = select_top2_sectors(bias_side)
        selected_stocks = fetch_stocks_from_sectors(sectors, bias_side)

        bias_done = True
        trading_active = True

        print(f"[BIAS] {bias_side} ADV={adv} DEC={dec}")
        print(f"[SECTOR] {sectors}")
        print(f"[L2] STOCKS={len(selected_stocks)}")

        # copy first 3 candles
        for s in selected_stocks:
            if s in candles_L1:
                candles_L2[s] = dict(list(candles_L1[s].items())[:3])
        l2_ready = True
        print("[L2] READY")

# ------------------------------------------------------------
# SIGNAL LOGIC
# ------------------------------------------------------------
def check_signal(sym, candle):
    vols = [c["vol"] for c in candles_L2[sym].values()]
    if candle["vol"] != min(vols):
        return

    if bias_side=="BUY" and candle["open"] > candle["close"]:
        signal_book[sym] = ("BUY", candle["high"], candle["low"])
        print(f"[SIGNAL] BUY {sym}")

    if bias_side=="SELL" and candle["close"] > candle["open"]:
        signal_book[sym] = ("SELL", candle["high"], candle["low"])
        print(f"[SIGNAL] SELL {sym}")

# ------------------------------------------------------------
# ORDER TRIGGER
# ------------------------------------------------------------
def try_entry(sym, ltp):
    global executed_trades
    if sym not in signal_book or executed_trades >= MAX_TRADES:
        return

    side, hi, lo = signal_book[sym]

    if side=="BUY" and ltp > hi:
        executed_trades += 1
        print(f"[ENTRY] BUY {sym} ({executed_trades}/5)")
        signal_book.pop(sym)

    if side=="SELL" and ltp < lo:
        executed_trades += 1
        print(f"[ENTRY] SELL {sym} ({executed_trades}/5)")
        signal_book.pop(sym)

    if executed_trades >= MAX_TRADES:
        print("[STOP] MAX TRADES HIT")

# ------------------------------------------------------------
# WS CALLBACK
# ------------------------------------------------------------
def on_message(msg):
    try:
        sym = msg.get("symbol")
        ltp = msg.get("ltp")
        vol = msg.get("last_traded_qty",0)
        ts = msg.get("exch_feed_time")

        if not sym or not ltp or not ts:
            return

        b = bucket_ts(ts)

        # -------- L1 --------
        candles_L1.setdefault(sym,{})
        if bucket_L1.get(sym) != b:
            if sym in bucket_L1:
                c = candles_L1[sym][bucket_L1[sym]]
                print(f"[L1] {sym} {tstr(bucket_L1[sym])} O:{c['open']} C:{c['close']} V:{c['vol']}")
            candles_L1[sym][b] = {"open":ltp,"high":ltp,"low":ltp,"close":ltp,"vol":vol}
            bucket_L1[sym] = b
        else:
            c = candles_L1[sym][b]
            c["high"]=max(c["high"],ltp)
            c["low"]=min(c["low"],ltp)
            c["close"]=ltp
            c["vol"]+=vol

        try_bias_switch()

        # -------- L2 --------
        if trading_active and l2_ready and sym in selected_stocks:
            candles_L2.setdefault(sym,{})
            if bucket_L2.get(sym)!=b:
                if sym in bucket_L2:
                    c2=candles_L2[sym][bucket_L2[sym]]
                    check_signal(sym,c2)
                candles_L2[sym][b]={"open":ltp,"high":ltp,"low":ltp,"close":ltp,"vol":vol}
                bucket_L2[sym]=b
            else:
                c2=candles_L2[sym][b]
                c2["high"]=max(c2["high"],ltp)
                c2["low"]=min(c2["low"],ltp)
                c2["close"]=ltp
                c2["vol"]+=vol

            try_entry(sym,ltp)

    except Exception as e:
        print("ERR:",e)

def on_connect():
    print("WS CONNECTED")
    fyers_ws.subscribe(symbols=list(selected_stocks) or [], data_type="SymbolUpdate")

def on_error(m): print("WS ERR",m)
def on_close(m): print("WS CLOSE",m)

# ------------------------------------------------------------
# WS START
# ------------------------------------------------------------
def start_ws():
    global fyers_ws
    fyers_ws=data_ws.FyersDataSocket(
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
if __name__=="__main__":
    app.run(host="0.0.0.0", port=PORT)
