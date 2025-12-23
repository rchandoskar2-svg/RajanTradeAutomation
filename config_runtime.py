# ============================================================
# config_runtime.py
# Runtime settings loader (NO fallback, env mandatory)
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
        try:
            r = requests.post(
                self.webapp_url,
                json={"action": "getSettings"},
                timeout=5
            )
            r.raise_for_status()
            self.settings = r.json().get("settings", {})
            self.last_fetch = datetime.now()
        except Exception as e:
            print("⚠️ Settings fetch failed:", e)

    def _get(self, key, default=None):
        return self.settings.get(key, default)

    def _time(self, key):
        v = self._get(key)
        h, m, s = map(int, v.split(":"))
        return dtime(h, m, s)

    # ---- PUBLIC ----
    def tick_start_time(self):
        return self._time("TICK_START_TIME")

    def bias_time(self):
        return self._time("BIAS_TIME")

    def bias_threshold(self):
        return float(self._get("BIAS_THRESHOLD_PERCENT", 80))
