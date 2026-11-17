"""Cài đặt người dùng, lưu ở %APPDATA%/NetTools/settings.json."""
import json
import os
import threading

from nettools.core.system import data_dir

DEFAULTS = {
    "theme": "dark",            # dark | light | system
    "unit": "Mbps",
    "close_to_tray": True,
    "notify": True,
    "monitor_autostart": True,
    "monitor_interval": 3,
    "monitor_host": "1.1.1.1",
    "adapter": "",
    "ping_host": "1.1.1.1",
}


class Settings:
    def __init__(self, path=None):
        self.path = path or os.path.join(data_dir(), "settings.json")
        self._lock = threading.Lock()
        self.data = dict(DEFAULTS)
        try:
            with open(self.path, encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                self.data.update({k: v for k, v in saved.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass

    def __getitem__(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key, value):
        with self._lock:
            self.data[key] = value
            tmp = self.path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self.path)
            except OSError:
                pass
