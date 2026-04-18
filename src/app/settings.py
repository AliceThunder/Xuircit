"""Application settings — persisted to ~/.xuircit/settings.json."""
from __future__ import annotations

import json
from pathlib import Path

_SETTINGS_FILE = Path.home() / ".xuircit" / "settings.json"

# Feature #4: Default shortcut definitions
# Format: {action_id: shortcut_string}
_DEFAULT_SHORTCUTS: dict[str, str] = {
    "file.new":        "Ctrl+N",
    "file.open":       "Ctrl+O",
    "file.save":       "Ctrl+S",
    "file.save_as":    "Ctrl+Shift+S",
    "file.exit":       "Alt+F4",
    "edit.undo":       "Ctrl+Z",
    "edit.redo":       "Ctrl+Y",
    "edit.select_all": "Ctrl+A",
    "edit.delete":     "Del",
    "view.zoom_in":    "Ctrl++",
    "view.zoom_out":   "Ctrl+-",
    "view.fit_all":    "Ctrl+0",
    "tools.select":    "Escape",
    "tools.rotate_cw": "R",
    "tools.flip_h":    "F",
    "tools.flip_v":    "V",
}

_DEFAULTS: dict = {
    "label_font_family": "monospace",
    "label_font_size": 8,
    "shortcuts": dict(_DEFAULT_SHORTCUTS),
}


class AppSettings:
    """Singleton for application-wide settings."""

    _instance: "AppSettings | None" = None

    def __new__(cls) -> "AppSettings":
        if cls._instance is None:
            obj = super().__new__(cls)
            obj._data: dict = dict(_DEFAULTS)
            obj._data["shortcuts"] = dict(_DEFAULT_SHORTCUTS)
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

    # Feature #4: shortcut support
    def shortcut(self, action_id: str) -> str:
        """Return the user-configured shortcut for action_id."""
        shortcuts = self._data.get("shortcuts", {})
        return str(shortcuts.get(action_id,
                                 _DEFAULT_SHORTCUTS.get(action_id, "")))

    def set_shortcut(self, action_id: str, keys: str) -> None:
        """Save a custom shortcut for action_id."""
        if "shortcuts" not in self._data:
            self._data["shortcuts"] = dict(_DEFAULT_SHORTCUTS)
        self._data["shortcuts"][action_id] = keys
        self._save()

    def all_shortcuts(self) -> dict[str, str]:
        """Return all shortcut mappings (action_id → key string)."""
        result = dict(_DEFAULT_SHORTCUTS)
        result.update(self._data.get("shortcuts", {}))
        return result

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if _SETTINGS_FILE.exists():
            try:
                with open(_SETTINGS_FILE, encoding="utf-8") as fh:
                    loaded = json.load(fh)
                # Merge shortcuts separately to preserve new defaults
                if "shortcuts" in loaded:
                    base = dict(_DEFAULT_SHORTCUTS)
                    base.update(loaded.pop("shortcuts"))
                    self._data["shortcuts"] = base
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
