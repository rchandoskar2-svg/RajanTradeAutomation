# ============================================================
# sector_engine.py
# Sector Bias + Stock Selection (TEST MODE)
# ============================================================

import requests
import time

# 🔴 TEMP TEST MAPPING (ONLY FOR TEST)
SECTOR_STOCKS_MAP = {
    "NIFTY AUTO": ["MARUTI", "TATAMOTORS", "M&M", "BAJAJ-AUTO", "HEROMOTOCO"],
    "NIFTY FMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "DABUR", "BRITANNIA"],
    "NIFTY IT": ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"],
    "NIFTY METAL": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "SAIL"],
    "NIFTY PHARMA": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "APOLLOHOSP"]
}

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com",
}

SESSION = requests.Session()
SESSION.headers.update(NSE_HEADERS)

def _warmup():
    SESSION.get("https://www.nseindia.com", timeout=10)

def fetch_sector_data(sector):
    _warmup()
    url = "https://www.nseindia.com/api/equity-stockIndices"
    res = SESSION.get(url, params={"index": sector}, timeout=10)
    data = res.json()

    stocks = {}
    for row in data.get("data", []):
        sym = row.get("symbol")
        chg = row.get("pChange")
        if sym and isinstance(chg, (int, float)):
            stocks[sym.upper()] = float(chg)
    return stocks

def run_sector_bias(sector_links):
    strong_sectors = []
    selected = set()

    for sector in sector_links.keys():
        stocks = fetch_sector_data(sector)

        total = len(stocks)
        up = len([v for v in stocks.values() if v > 0])
        down = len([v for v in stocks.values() if v < 0])

        if total == 0:
            continue

        up_pct = (up / total) * 100
        down_pct = (down / total) * 100

        bias = None
        if up_pct >= 80:
            bias = "BUY"
        elif down_pct >= 80:
            bias = "SELL"

        if not bias:
            continue

        strong_sectors.append({
            "sector": sector,
            "bias": bias,
            "up_pct": round(up_pct, 2),
            "down_pct": round(down_pct, 2)
        })

        allowed = set(SECTOR_STOCKS_MAP.get(sector, []))
        for sym, pct in stocks.items():
            if sym in allowed and abs(pct) <= 2.5:
                selected.add(sym)

        time.sleep(0.5)

    return strong_sectors, sorted(selected)
