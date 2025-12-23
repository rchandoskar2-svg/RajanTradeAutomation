# ============================================================
# config_runtime.py
# Single source of truth for ALL timings
# ============================================================

import os
import requests
from datetime import datetime, time as dtime

class RuntimeConfig:
    def __init__(self):
        self.webapp_url = os.getenv("WEBAPP_URL")
        if not self.webapp_url:
            raise RuntimeError("WEBAPP_URL env variable missing")

        self.settings = {}
        self.last_fetch = None

    def refresh(self):
        r = requests.post(
            self.webapp_url,
            json={"action": "getSettings"},
            timeout=5
        )
        r.raise_for_status()
        self.settings = r.json().get("settings", {})
        self.last_fetch = datetime.now()

    def _get(self, key):
        return self.settings.get(key)

    def _time(self, key):
        h, m, s = map(int, self._get(key).split(":"))
        return dtime(h, m, s)

    # ===== PUBLIC =====
    def tick_start_time(self):
        return self._time("TICK_START_TIME")

    def bias_time(self):
        return self._time("BIAS_TIME")

    def max_up(self):
        return float(self._get("MAX_UP_PERCENT"))

    def max_down(self):
        return float(self._get("MAX_DOWN_PERCENT"))
