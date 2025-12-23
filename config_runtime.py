# ============================================================
# config_runtime.py
# Single source of truth for ALL timings
# ============================================================

import requests
from datetime import datetime

SETTINGS_URL = "YOUR_WEBAPP_URL?action=getSettings"

class RuntimeConfig:
    def __init__(self):
        self.reload()

    def reload(self):
        data = requests.get(SETTINGS_URL, timeout=5).json()

        self.tick_start_time = data.get("TICK_START_TIME", "09:15:00")
        self.bias_time = data.get("BIAS_TIME", "09:25:05")
        self.candle_interval = int(data.get("CANDLE_INTERVAL", 300))

    def now_str(self):
        return datetime.now().strftime("%H:%M:%S")

    def tick_allowed(self):
        return self.now_str() >= self.tick_start_time

    def bias_allowed(self):
        return self.now_str() >= self.bias_time


RUNTIME = RuntimeConfig()
