"""Component library: definitions of all supported schematic components."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ComponentDef:
    type_name: str
    category: str
    display_name: str
    description: str
    pins: list[str]
    default_value: str = ""
    default_params: dict[str, Any] = field(default_factory=dict)
    ref_prefix: str = "X"


class ComponentLibrary:
    """Singleton registry of all component definitions."""

    _instance: "ComponentLibrary | None" = None

    def __new__(cls) -> "ComponentLibrary":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._registry: dict[str, ComponentDef] = {}
            cls._instance._build()
        return cls._instance

    # ------------------------------------------------------------------

    def _build(self) -> None:
        defs: list[ComponentDef] = [
            # ── Passive ──────────────────────────────────────────────
            ComponentDef("R", "Passive", "Resistor", "Ideal resistor",
                         ["p", "n"], "1k", {}, "R"),
            ComponentDef("C", "Passive", "Capacitor", "Ideal capacitor",
                         ["+", "-"], "100n", {}, "C"),
            ComponentDef("L", "Passive", "Inductor", "Ideal inductor",
                         ["p", "n"], "10u", {}, "L"),
            ComponentDef("T", "Passive", "Transformer",
                         "Coupled inductors / transformer",
                         ["p1", "p2", "s1", "s2"], "", {}, "T"),
            # ── Sources ──────────────────────────────────────────────
            ComponentDef("V", "Sources", "Voltage Source",
                         "Independent voltage source",
                         ["+", "-"], "5", {}, "V"),
            ComponentDef("I", "Sources", "Current Source",
                         "Independent current source",
                         ["+", "-"], "1m", {}, "I"),
            ComponentDef("E", "Sources", "VCVS",
                         "Voltage-controlled voltage source",
                         ["+", "-", "nc+", "nc-"], "1", {}, "E"),
            ComponentDef("F", "Sources", "CCCS",
                         "Current-controlled current source",
                         ["+", "-", "nc+", "nc-"], "1", {}, "F"),
            ComponentDef("G", "Sources", "VCCS",
                         "Voltage-controlled current source",
                         ["+", "-", "nc+", "nc-"], "1", {}, "G"),
            ComponentDef("H", "Sources", "CCVS",
                         "Current-controlled voltage source",
                         ["+", "-", "nc+", "nc-"], "1", {}, "H"),
            # ── Semiconductors ────────────────────────────────────────
            ComponentDef("D", "Semiconductors", "Diode",
                         "PN junction diode",
                         ["anode", "cathode"], "1N4148", {}, "D"),
            ComponentDef("Z", "Semiconductors", "Zener Diode",
                         "Zener diode",
                         ["anode", "cathode"], "BZX55C5V1", {}, "D"),
            ComponentDef("Q_NPN", "Semiconductors", "NPN BJT",
                         "NPN bipolar junction transistor",
                         ["base", "collector", "emitter"], "2N2222", {}, "Q"),
            ComponentDef("Q_PNP", "Semiconductors", "PNP BJT",
                         "PNP bipolar junction transistor",
                         ["base", "collector", "emitter"], "2N2907", {}, "Q"),
            ComponentDef("M_NMOS", "Semiconductors", "NMOS FET",
                         "N-channel MOSFET",
                         ["gate", "drain", "source", "body"], "IRF540", {}, "M"),
            ComponentDef("M_PMOS", "Semiconductors", "PMOS FET",
                         "P-channel MOSFET",
                         ["gate", "drain", "source", "body"], "IRF9540", {}, "M"),
            ComponentDef("IGBT", "Semiconductors", "IGBT",
                         "Insulated-gate bipolar transistor",
                         ["gate", "collector", "emitter"], "IRGB4062", {}, "Q"),
            # ── Power Electronics ─────────────────────────────────────
            ComponentDef("SW", "Power Electronics", "Ideal Switch",
                         "Ideal controlled switch",
                         ["p", "n"], "", {}, "SW"),
            ComponentDef("SCR", "Power Electronics", "SCR / Thyristor",
                         "Silicon controlled rectifier",
                         ["anode", "cathode", "gate"], "TYN612", {}, "SCR"),
            ComponentDef("TRIAC", "Power Electronics", "TRIAC",
                         "Bidirectional thyristor",
                         ["MT1", "MT2", "gate"], "BTA12", {}, "TRIAC"),
            # ── Wiring ────────────────────────────────────────────────
            ComponentDef("GND", "Wiring", "Ground",
                         "Ground / reference node",
                         ["p"], "", {}, "GND"),
            ComponentDef("NETLABEL", "Wiring", "Net Label",
                         "Named net label",
                         ["p"], "", {}, "NET"),
            ComponentDef("JUNCTION", "Wiring", "Junction",
                         "Wire junction dot",
                         [], "", {}, "J"),
        ]
        for d in defs:
            self._registry[d.type_name] = d

    # ------------------------------------------------------------------

    def get(self, type_name: str) -> ComponentDef | None:
        return self._registry.get(type_name)

    def all(self) -> list[ComponentDef]:
        return list(self._registry.values())

    def by_category(self, category: str) -> list[ComponentDef]:
        return [d for d in self._registry.values() if d.category == category]

    def categories(self) -> list[str]:
        seen: list[str] = []
        for d in self._registry.values():
            if d.category not in seen:
                seen.append(d.category)
        return seen
