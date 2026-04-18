"""Application settings — persisted to ~/.xuircit/settings.json."""
from __future__ import annotations

import json
from pathlib import Path

_SETTINGS_FILE = Path.home() / ".xuircit" / "settings.json"

_DEFAULTS: dict = {
    "label_font_family": "monospace",
    "label_font_size": 8,
}


class AppSettings:
    """Singleton for application-wide settings."""

    _instance: "AppSettings | None" = None

    def __new__(cls) -> "AppSettings":
        if cls._instance is None:
            obj = super().__new__(cls)
            obj._data: dict = dict(_DEFAULTS)
            obj._load()
            cls._instance = obj
        return cls._instance

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def get(self, key: str, default=None):
        return self._data.get(key, _DEFAULTS.get(key, default))

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self._save()

    def label_font_family(self) -> str:
        return str(self.get("label_font_family", "monospace"))

    def label_font_size(self) -> int:
        return int(self.get("label_font_size", 8))

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if _SETTINGS_FILE.exists():
            try:
                with open(_SETTINGS_FILE, encoding="utf-8") as fh:
                    loaded = json.load(fh)
                self._data.update(loaded)
            except Exception:
                pass

    def _save(self) -> None:
        try:
            _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_SETTINGS_FILE, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
        except Exception:
            pass

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None
