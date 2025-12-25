# ============================================================
# sector_engine.py
# Sector Bias + Stock Selection (NSE REAL DATA)
# ============================================================

import requests
import time
from sectormapping import SECTOR_STOCKS_MAP

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com",
}

SESSION = requests.Session()
SESSION.headers.update(NSE_HEADERS)

def _warmup_nse():
    # NSE requires homepage hit before API
    SESSION.get("https://www.nseindia.com", timeout=10)

def fetch_sector_data(sector_symbol):
    """
    sector_symbol example:
    NIFTY AUTO
    """
    _warmup_nse()

    url = "https://www.nseindia.com/api/equity-stockIndices"
    params = {"index": sector_symbol}

    res = SESSION.get(url, params=params, timeout=10)
    data = res.json()

    stocks = {}
    for row in data.get("data", []):
        symbol = row.get("symbol", "").upper()
        pchange = row.get("pChange")

        if symbol and isinstance(pchange, (int, float)):
            stocks[symbol] = float(pchange)

    return stocks


def calculate_sector_bias(stocks: dict):
    total = len(stocks)
    up = len([v for v in stocks.values() if v > 0])
    down = len([v for v in stocks.values() if v < 0])

    if total == 0:
        return None, 0, 0

    up_pct = (up / total) * 100
    down_pct = (down / total) * 100

    if up_pct >= 80:
        return "BUY", up_pct, down_pct
    if down_pct >= 80:
        return "SELL", up_pct, down_pct

    return None, up_pct, down_pct


def run_sector_bias(sector_links: dict):
    """
    sector_links = {
      "NIFTY AUTO": "...",
      ...
    }
    """
    strong_sectors = []
    selected_stocks = set()

    for sector_name in sector_links.keys():
        stocks = fetch_sector_data(sector_name)
        bias, up_pct, down_pct = calculate_sector_bias(stocks)

        if not bias:
            continue

        strong_sectors.append({
            "sector": sector_name,
            "bias": bias,
            "up_pct": round(up_pct, 2),
            "down_pct": round(down_pct, 2),
            "total_stocks": len(stocks)
        })

        allowed = set(SECTOR_STOCKS_MAP.get(sector_name, []))

        for sym, pct in stocks.items():
            if sym in allowed and abs(pct) <= 2.5:
                selected_stocks.add(sym)

        time.sleep(0.5)  # NSE safety

    return strong_sectors, sorted(selected_stocks)
