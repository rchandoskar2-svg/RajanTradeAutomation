# ============================================================
# config_runtime.py
# Runtime settings loader from Google Sheet (WebApp)
# Controls ALL time windows (editable)
# ============================================================

import requests
from datetime import datetime, time as dtime

# ------------------------------------------------------------
# DEFAULTS (SAFE FALLBACKS)
# ------------------------------------------------------------
DEFAULTS = {
    "TICK_START_TIME": "10:39:00",
    "BIAS_TIME_INFO": "10:50:05",
    "BIAS_THRESHOLD_PERCENT": "80",
    "MAX_UP_PERCENT": "2.5",
    "MAX_DOWN_PERCENT": "-2.5",
    "BUY_SECTOR_COUNT": "2",
    "SELL_SECTOR_COUNT": "2",
    "MAX_TRADES_PER_DAY": "5"
}

class RuntimeConfig:
    def __init__(self, webapp_url: str):
        self.webapp_url = webapp_url
        self.settings = {}
        self.last_fetch_ts = None

    # --------------------------------------------------------
    # Fetch ALL settings from Google Sheet
    # --------------------------------------------------------
    def refresh(self):
        try:
            r = requests.post(
                self.webapp_url,
                json={"action": "getSettings"},
                timeout=5
            )
            if r.status_code == 200:
                data = r.json().get("settings", {})
                self.settings = {**DEFAULTS, **data}
                self.last_fetch_ts = datetime.now()
        except Exception:
            # silent fail → defaults stay active
            self.settings = DEFAULTS.copy()

    # --------------------------------------------------------
    # Helpers
    # --------------------------------------------------------
    def _get(self, key):
        return self.settings.get(key, DEFAULTS.get(key))

    def _time(self, key):
        v = self._get(key)
        try:
            h, m, s = map(int, v.split(":"))
            return dtime(h, m, s)
        except:
            h, m, s = map(int, DEFAULTS[key].split(":"))
            return dtime(h, m, s)

    # --------------------------------------------------------
    # PUBLIC ACCESSORS (USED BY ENGINE)
    # --------------------------------------------------------
    def tick_start_time(self):
        return self._time("TICK_START_TIME")

    def bias_time(self):
        return self._time("BIAS_TIME_INFO")

    def bias_threshold(self):
        return float(self._get("BIAS_THRESHOLD_PERCENT"))

    def max_up_percent(self):
        return float(self._get("MAX_UP_PERCENT"))

    def max_down_percent(self):
        return float(self._get("MAX_DOWN_PERCENT"))

    def buy_sector_count(self):
        return int(self._get("BUY_SECTOR_COUNT"))

    def sell_sector_count(self):
        return int(self._get("SELL_SECTOR_COUNT"))

    def max_trades(self):
        return int(self._get("MAX_TRADES_PER_DAY"))

    # --------------------------------------------------------
    # TIME CHECKS
    # --------------------------------------------------------
    def is_tick_window_open(self, now: datetime):
        return now.time() >= self.tick_start_time()

    def is_bias_time(self, now: datetime):
        return now.time() >= self.bias_time()
