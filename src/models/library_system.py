"""Unified component library system.

All component definitions – both built-in (preset) and user-defined – are
managed here through a single ``LibraryManager`` singleton.  Multiple named
libraries are supported; each is persisted as a JSON file under
``~/.xuircit/libraries/``.

Library structure
-----------------
Every library is a :class:`CompLibrary` with a stable ``library_id``, a
human-readable ``name``, and a collection of :class:`LibEntry` objects.

``LibEntry`` is the unified component descriptor:
* ``is_builtin = True`` → the type is rendered by a registered
  :class:`~components.base.ComponentItem` subclass (the classic built-in
  symbols like ResistorItem).
* ``is_builtin = False`` → the type uses a custom symbol built from
  ``pins`` / ``symbol`` lists (user-drawn components).

Component lookup
----------------
The *full key* of a component is ``(library_id, type_name)``.  When a
library is not specified, ``LibraryManager.find_entry`` searches all
libraries in order (preset first).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

_LIBRARIES_DIR = Path.home() / ".xuircit" / "libraries"
PRESET_LIBRARY_ID = "preset"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class LibEntry:
    """Unified component entry – works for both built-in and user-defined."""

    type_name: str
    display_name: str
    category: str
    description: str
    ref_prefix: str = "X"
    default_value: str = ""
    default_params: dict[str, Any] = field(default_factory=dict)
    # For built-in types: simple pin names (ordering matches the renderer)
    pin_names: list[str] = field(default_factory=list)
    # For user-defined types: full pin definitions [{name, x, y}, ...]
    pins: list[dict[str, Any]] = field(default_factory=list)
    # User-defined drawing commands [{kind, x1, y1, x2, y2, w, h, text}, ...]
    symbol: list[dict[str, Any]] = field(default_factory=list)
    # True ⟹ rendered by a registered ComponentItem subclass
    is_builtin: bool = True
    ref_label_offset: list[float] = field(default_factory=lambda: [0.0, -22.0])
    val_label_offset: list[float] = field(default_factory=lambda: [0.0, 14.0])
    # Extra named labels (for user-defined components).
    # Each item: {"text": str, "side": str, "order": int, "default_value": str}
    labels: list[dict] = field(default_factory=list)
    # Fix 3: True ⟹ component is a virtual (non-SPICE) wiring helper.
    # Virtual components are saved in .xcit_virtual rather than as SPICE elements.
    is_virtual: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LibEntry":
        return cls(
            type_name=d["type_name"],
            display_name=d.get("display_name", d["type_name"]),
            category=d.get("category", "User"),
            description=d.get("description", ""),
            ref_prefix=d.get("ref_prefix", "X"),
            default_value=d.get("default_value", ""),
            default_params=d.get("default_params", {}),
            pin_names=d.get("pin_names", []),
            pins=d.get("pins", []),
            symbol=d.get("symbol", []),
            is_builtin=d.get("is_builtin", True),
            ref_label_offset=d.get("ref_label_offset", [0.0, -22.0]),
            val_label_offset=d.get("val_label_offset", [0.0, 14.0]),
            labels=d.get("labels", []),
            is_virtual=d.get("is_virtual", False),
        )


# ---------------------------------------------------------------------------
# Single library container
# ---------------------------------------------------------------------------

class CompLibrary:
    """A named collection of component entries."""

    def __init__(self, library_id: str, name: str,
                 is_preset: bool = False) -> None:
        self.library_id = library_id
        self.name = name
        self.is_preset = is_preset
        self._entries: dict[str, LibEntry] = {}

    # ---- access ----

    def get(self, type_name: str) -> LibEntry | None:
        return self._entries.get(type_name)

    def all(self) -> list[LibEntry]:
        return list(self._entries.values())

    def add(self, entry: LibEntry) -> None:
        self._entries[entry.type_name] = entry

    def remove(self, type_name: str) -> None:
        self._entries.pop(type_name, None)

    def categories(self) -> list[str]:
        seen: list[str] = []
        for e in self._entries.values():
            if e.category not in seen:
                seen.append(e.category)
        return seen

    def by_category(self, category: str) -> list[LibEntry]:
        return [e for e in self._entries.values() if e.category == category]

    # ---- serialisation ----

    def to_dict(self) -> dict[str, Any]:
        return {
            "library_id": self.library_id,
            "name": self.name,
            "is_preset": self.is_preset,
            "components": [e.to_dict() for e in self._entries.values()],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CompLibrary":
        lib = cls(
            library_id=d["library_id"],
            name=d["name"],
            is_preset=d.get("is_preset", False),
        )
        for cd in d.get("components", []):
            lib.add(LibEntry.from_dict(cd))
        return lib


# ---------------------------------------------------------------------------
# Library manager (singleton)
# ---------------------------------------------------------------------------

class LibraryManager:
    """Singleton that manages all component libraries."""

    _instance: "LibraryManager | None" = None

    def __new__(cls) -> "LibraryManager":
        if cls._instance is None:
            obj = super().__new__(cls)
            obj._libraries: list[CompLibrary] = []
            obj._init()
            cls._instance = obj
        return cls._instance

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init(self) -> None:
        """Always build the preset library from hardcoded defaults.

        Fix 2: The preset library is never loaded from or saved to disk.
        This guarantees the preset always contains correct, consistent
        component definitions.  User modifications should be made in
        user-created libraries instead.
        """
        preset = self._build_preset()
        self._libraries = [preset]

        # Load other user libraries
        if _LIBRARIES_DIR.exists():
            for path in sorted(_LIBRARIES_DIR.glob("*.json")):
                if path.stem == PRESET_LIBRARY_ID:
                    continue
                try:
                    with open(path, encoding="utf-8") as fh:
                        data = json.load(fh)
                    lib = CompLibrary.from_dict(data)
                    self._libraries.append(lib)
                except Exception:
                    pass

        # Migrate legacy user_components.json if present and no user libs yet
        self._migrate_legacy()

    def _migrate_legacy(self) -> None:
        """One-time migration of ~/.xuircit/user_components.json."""
        legacy = Path.home() / ".xuircit" / "user_components.json"
        if not legacy.exists():
            return
        # Only migrate if no user (non-preset) library exists yet
        user_libs = [lb for lb in self._libraries if not lb.is_preset]
        if user_libs:
            return
        try:
            with open(legacy, encoding="utf-8") as fh:
                data = json.load(fh)
            comps = data.get("components", [])
            if not comps:
                return
            ulib = CompLibrary(str(uuid.uuid4()), "User Library")
            for cd in comps:
                entry = LibEntry(
                    type_name=cd["type_name"],
                    display_name=cd.get("display_name", cd["type_name"]),
                    category=cd.get("category", "User"),
                    description=cd.get("description", ""),
                    ref_prefix=cd.get("ref_prefix", "U"),
                    default_value=cd.get("default_value", ""),
                    pin_names=[],
                    pins=cd.get("pins", []),
                    symbol=cd.get("symbol", []),
                    is_builtin=False,
                    ref_label_offset=cd.get("ref_label_offset", [0.0, -22.0]),
                    val_label_offset=cd.get("val_label_offset", [0.0, 14.0]),
                )
                ulib.add(entry)
            self._libraries.append(ulib)
            self._save_library(ulib)
            # Rename the legacy file so it is not re-imported
            legacy.rename(legacy.with_suffix(".json.migrated"))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Preset library builder (hardcoded defaults)
    # ------------------------------------------------------------------

    def _build_preset(self) -> CompLibrary:
        lib = CompLibrary(PRESET_LIBRARY_ID, "Preset Library", is_preset=True)
        defs = [
            # ── Passive ──────────────────────────────────────────────
            ("R", "Passive", "Resistor", "Ideal resistor",
             ["p", "n"], "1k", {}, "R"),
            ("C", "Passive", "Capacitor", "Ideal capacitor",
             ["+", "-"], "100n", {}, "C"),
            ("L", "Passive", "Inductor", "Ideal inductor",
             ["p", "n"], "10u", {}, "L"),
            ("T", "Passive", "Transformer",
             "Coupled inductors / transformer",
             ["p1", "p2", "s1", "s2"], "", {}, "T"),
            # ── Sources ──────────────────────────────────────────────
            ("V", "Sources", "Voltage Source",
             "Independent voltage source",
             ["+", "-"], "5", {}, "V"),
            ("I", "Sources", "Current Source",
             "Independent current source",
             ["+", "-"], "1m", {}, "I"),
            ("E", "Sources", "VCVS",
             "Voltage-controlled voltage source",
             ["+", "-", "nc+", "nc-"], "1", {}, "E"),
            ("F", "Sources", "CCCS",
             "Current-controlled current source",
             ["+", "-", "nc+", "nc-"], "1", {}, "F"),
            ("G", "Sources", "VCCS",
             "Voltage-controlled current source",
             ["+", "-", "nc+", "nc-"], "1", {}, "G"),
            ("H", "Sources", "CCVS",
             "Current-controlled voltage source",
             ["+", "-", "nc+", "nc-"], "1", {}, "H"),
            # ── Semiconductors ────────────────────────────────────────
            ("D", "Semiconductors", "Diode",
             "PN junction diode",
             ["anode", "cathode"], "1N4148", {}, "D"),
            ("Z", "Semiconductors", "Zener Diode",
             "Zener diode",
             ["anode", "cathode"], "BZX55C5V1", {}, "D"),
            ("Q_NPN", "Semiconductors", "NPN BJT",
             "NPN bipolar junction transistor",
             ["base", "collector", "emitter"], "2N2222", {}, "Q"),
            ("Q_PNP", "Semiconductors", "PNP BJT",
             "PNP bipolar junction transistor",
             ["base", "collector", "emitter"], "2N2907", {}, "Q"),
            ("M_NMOS", "Semiconductors", "NMOS FET",
             "N-channel MOSFET",
             ["gate", "drain", "source", "body"], "IRF540", {}, "M"),
            ("M_PMOS", "Semiconductors", "PMOS FET",
             "P-channel MOSFET",
             ["gate", "drain", "source", "body"], "IRF9540", {}, "M"),
            ("IGBT", "Semiconductors", "IGBT",
             "Insulated-gate bipolar transistor",
             ["gate", "collector", "emitter"], "IRGB4062", {}, "Q"),
            # ── Power Electronics ─────────────────────────────────────
            ("SW", "Power Electronics", "Ideal Switch",
             "Ideal controlled switch",
             ["p", "n"], "", {}, "SW"),
            ("SCR", "Power Electronics", "SCR / Thyristor",
             "Silicon controlled rectifier",
             ["anode", "cathode", "gate"], "TYN612", {}, "SCR"),
            ("TRIAC", "Power Electronics", "TRIAC",
             "Bidirectional thyristor",
             ["MT1", "MT2", "gate"], "BTA12", {}, "TRIAC"),
            # ── Wiring ────────────────────────────────────────────────
            ("GND", "Wiring", "Ground",
             "Ground / reference node",
             ["p"], "", {}, "GND"),
            ("NETLABEL", "Wiring", "Net Label",
             "Named net label",
             ["p"], "", {}, "NET"),
            ("JUNCTION", "Wiring", "Junction",
             "Wire junction dot",
             [], "", {}, "J"),
            ("ELBOW", "Wiring", "Elbow (90° bend)",
             "Right-angle wire connector — connects two wires at a 90° corner",
             ["a", "b"], "", {}, "J"),
            ("TEE", "Wiring", "Tee (T-junction)",
             "T-junction wire connector — connects three wires",
             ["left", "right", "down"], "", {}, "J"),
        ]
        for (tn, cat, disp, desc, pins, val, params, pfx) in defs:
            lib.add(LibEntry(
                type_name=tn,
                display_name=disp,
                category=cat,
                description=desc,
                ref_prefix=pfx,
                default_value=val,
                default_params=params,
                pin_names=pins,
                pins=[],
                symbol=[],
                is_builtin=True,
            ))
        return lib

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def all_libraries(self) -> list[CompLibrary]:
        return list(self._libraries)

    def get_library(self, library_id: str) -> CompLibrary | None:
        for lib in self._libraries:
            if lib.library_id == library_id:
                return lib
        return None

    def find_entry(
        self, type_name: str, library_id: str | None = None
    ) -> tuple[LibEntry, str] | None:
        """Return (entry, library_id) or None.

        If *library_id* is given, that library is searched first.
        Falls back to searching all libraries in order.
        """
        if library_id:
            lib = self.get_library(library_id)
            if lib:
                entry = lib.get(type_name)
                if entry:
                    return entry, library_id
        for lib in self._libraries:
            entry = lib.get(type_name)
            if entry:
                return entry, lib.library_id
        return None

    # ------------------------------------------------------------------
    # Library management
    # ------------------------------------------------------------------

    def add_library(self, name: str) -> CompLibrary:
        lib = CompLibrary(str(uuid.uuid4()), name, is_preset=False)
        self._libraries.append(lib)
        self._save_library(lib)
        return lib

    def remove_library(self, library_id: str) -> None:
        if library_id == PRESET_LIBRARY_ID:
            return  # Preset library cannot be removed
        lib = self.get_library(library_id)
        if lib:
            self._libraries.remove(lib)
            path = _LIBRARIES_DIR / f"{library_id}.json"
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    def rename_library(self, library_id: str, new_name: str) -> None:
        lib = self.get_library(library_id)
        if lib:
            lib.name = new_name
            self._save_library(lib)

    # ------------------------------------------------------------------
    # Component management
    # ------------------------------------------------------------------

    def save_entry(self, library_id: str, entry: LibEntry) -> None:
        lib = self.get_library(library_id)
        if lib is None:
            return
        lib.add(entry)
        self._save_library(lib)

    def delete_entry(self, library_id: str, type_name: str) -> None:
        lib = self.get_library(library_id)
        if lib is None:
            return
        lib.remove(type_name)
        self._save_library(lib)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_library(self, lib: CompLibrary) -> None:
        # Fix 2: Never save the preset library to disk; it is always rebuilt
        # from hardcoded defaults on startup.
        if lib.library_id == PRESET_LIBRARY_ID:
            return
        try:
            _LIBRARIES_DIR.mkdir(parents=True, exist_ok=True)
            path = _LIBRARIES_DIR / f"{lib.library_id}.json"
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(lib.to_dict(), fh, indent=2)
        except Exception:
            pass

    def save_all(self) -> None:
        for lib in self._libraries:
            self._save_library(lib)

    # ------------------------------------------------------------------
    # Reset (for testing / after external edits)
    # ------------------------------------------------------------------

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None
