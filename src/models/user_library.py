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
    kind: str           # "line" | "rect" | "ellipse" | "text" | "polyline"
    # Common fields (not all required for every kind)
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0
    w: float = 0.0
    h: float = 0.0
    text: str = ""
    filled: bool = False  # Issue 6: solid fill for rect/ellipse/polyline
    # Polyline: list of [x, y] pairs (used when kind == "polyline")
    points: list = field(default_factory=list)


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
    dx, dy       : Explicit position offset from component origin for the
                   horizontal (default) perspective. (Feature 6)
    dx_v, dy_v   : Position offset for the vertical (rotated 90°) perspective.
                   (Feature 8) — if [0,0] the horizontal values are used.
    font_family  : Font family for this label; empty = use the application default.
    font_size    : Font size; 0 = use the application default.
    bold         : Bold text flag. (Feature 7)
    italic       : Italic text flag. (Feature 7)
    color        : Hex color string; empty = use the component body color.
    alignment    : Text alignment: "left", "center", or "right". (Feature 7)
    use_offset   : When True the dx/dy (or dx_v/dy_v) offset is used instead
                   of the automatic side-based layout. (Feature 6)
    """
    text: str
    side: str = "top"   # "left" | "right" | "top" | "bottom"
    order: int = 0
    default_value: str = ""  # Issue 12: default value displayed next to component
    # Feature 6: explicit position offset (horizontal perspective)
    dx: float = 0.0
    dy: float = 0.0
    # Feature 8: explicit position offset (vertical / rotated perspective)
    dx_v: float = 0.0
    dy_v: float = 0.0
    # Feature 7: per-label style
    font_family: str = ""   # empty = application default
    font_size: int = 0      # 0 = application default
    bold: bool = False
    italic: bool = False
    color: str = ""         # empty = component body color
    alignment: str = "left"  # "left" | "center" | "right"
    # Feature 6: whether to use the explicit dx/dy instead of auto-side layout
    use_offset: bool = False


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
    # Feature 8: vertical (rotated) perspective offsets
    ref_label_offset_v: list[float] = field(default_factory=list)
    val_label_offset_v: list[float] = field(default_factory=list)
    # Feature 7: per-label style for ref and val labels
    # Each style dict may contain: font_family, font_size, bold, italic, color, alignment
    ref_label_style: dict = field(default_factory=dict)
    val_label_style: dict = field(default_factory=dict)
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
                    points=s.get("points", []),
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
                    dx=lb.get("dx", 0.0),
                    dy=lb.get("dy", 0.0),
                    dx_v=lb.get("dx_v", 0.0),
                    dy_v=lb.get("dy_v", 0.0),
                    font_family=lb.get("font_family", ""),
                    font_size=lb.get("font_size", 0),
                    bold=lb.get("bold", False),
                    italic=lb.get("italic", False),
                    color=lb.get("color", ""),
                    alignment=lb.get("alignment", "left"),
                    use_offset=lb.get("use_offset", False),
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
            ref_label_offset_v=d.get("ref_label_offset_v", []),
            val_label_offset_v=d.get("val_label_offset_v", []),
            ref_label_style=d.get("ref_label_style", {}),
            val_label_style=d.get("val_label_style", {}),
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
