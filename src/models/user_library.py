"""User-defined component library — save/load from disk."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# Storage location: ~/.xuircit/user_components.json
_USER_DIR = Path.home() / ".xuircit"
_USER_FILE = _USER_DIR / "user_components.json"


@dataclass
class PinDef:
    name: str
    x: float
    y: float


@dataclass
class SymbolCmd:
    """One drawing command for the symbol."""
    kind: str           # "line" | "rect" | "ellipse" | "text"
    # Common fields (not all required for every kind)
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    w: float = 0.0
    h: float = 0.0
    text: str = ""
    filled: bool = False  # Issue 6: solid fill for rect/ellipse


@dataclass
class LabelDef:
    """Definition of an extra property attached to a user-defined component.

    Attributes
    ----------
    text         : Property name (key in the component's params dict).
    side         : Which side of the component body the label sits on.
                   One of ``"left"``, ``"right"``, ``"top"``, ``"bottom"``.
    order        : Integer used to sequence multiple labels on the same side
                   (smaller = closer to the component body edge).
    default_value: Default display value shown next to the component when no
                   instance-specific value is set.  (Issue 12)
    """
    text: str
    side: str = "top"   # "left" | "right" | "top" | "bottom"
    order: int = 0
    default_value: str = ""  # Issue 12: default value displayed next to component


@dataclass
class UserCompDef:
    type_name: str
    display_name: str
    category: str = "User"
    description: str = ""
    ref_prefix: str = "U"
    default_value: str = ""
    pins: list[PinDef] = field(default_factory=list)
    symbol: list[SymbolCmd] = field(default_factory=list)
    # Label positions as [dx, dy] offsets relative to component centre.
    # None means use the built-in default.
    ref_label_offset: list[float] = field(default_factory=lambda: [0.0, -22.0])
    val_label_offset: list[float] = field(default_factory=lambda: [0.0, 14.0])
    # Extra named labels beyond ref/value (order within a side is preserved).
    labels: list[LabelDef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "UserCompDef":
        pins = [PinDef(**p) for p in d.get("pins", [])]
        symbol_raw = d.get("symbol", [])
        # Build SymbolCmd objects, tolerating missing fields (backward compat)
        symbol: list[SymbolCmd] = []
        for s in symbol_raw:
            try:
                symbol.append(SymbolCmd(
                    kind=s.get("kind", "line"),
                    x1=s.get("x1", 0.0),
                    y1=s.get("y1", 0.0),
                    x2=s.get("x2", 0.0),
                    y2=s.get("y2", 0.0),
                    w=s.get("w", 0.0),
                    h=s.get("h", 0.0),
                    text=s.get("text", ""),
                    filled=s.get("filled", False),
                ))
            except Exception:
                pass
        raw_labels = d.get("labels", [])
        labels: list[LabelDef] = []
        for lb in raw_labels:
            try:
                labels.append(LabelDef(
                    text=lb.get("text", ""),
                    side=lb.get("side", "top"),
                    order=lb.get("order", 0),
                    default_value=lb.get("default_value", ""),
                ))
            except Exception:
                pass
        return cls(
            type_name=d["type_name"],
            display_name=d.get("display_name", d["type_name"]),
            category=d.get("category", "User"),
            description=d.get("description", ""),
            ref_prefix=d.get("ref_prefix", "U"),
            default_value=d.get("default_value", ""),
            pins=pins,
            symbol=symbol,
            ref_label_offset=d.get("ref_label_offset", [0.0, -22.0]),
            val_label_offset=d.get("val_label_offset", [0.0, 14.0]),
            labels=labels,
        )


class UserLibrary:
    """Singleton that loads/saves user-defined component definitions."""

    _instance: "UserLibrary | None" = None

    def __new__(cls) -> "UserLibrary":
        if cls._instance is None:
            obj = super().__new__(cls)
            obj._defs: dict[str, UserCompDef] = {}
            obj._load()
            cls._instance = obj
        return cls._instance

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get(self, type_name: str) -> UserCompDef | None:
        return self._defs.get(type_name)

    def all(self) -> list[UserCompDef]:
        return list(self._defs.values())

    def save_def(self, udef: UserCompDef) -> None:
        self._defs[udef.type_name] = udef
        self._persist()

    def delete_def(self, type_name: str) -> None:
        self._defs.pop(type_name, None)
        self._persist()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not _USER_FILE.exists():
            return
        try:
            with open(_USER_FILE, encoding="utf-8") as fh:
                data = json.load(fh)
            for item in data.get("components", []):
                udef = UserCompDef.from_dict(item)
                self._defs[udef.type_name] = udef
        except Exception:
            pass  # Corrupt file — start fresh

    def _persist(self) -> None:
        try:
            _USER_DIR.mkdir(parents=True, exist_ok=True)
            data = {"components": [d.to_dict() for d in self._defs.values()]}
            with open(_USER_FILE, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except Exception:
            pass

    def reload(self) -> None:
        """Force reload from disk (call after external edit)."""
        self._defs.clear()
        self._load()

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton so it reloads on next access."""
        cls._instance = None
