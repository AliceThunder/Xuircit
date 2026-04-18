"""SPICE netlist parser — converts netlist text to component dicts."""
from __future__ import annotations

import re
from typing import Any

# Map first-character element type to internal type name
_FIRST_CHAR_MAP: dict[str, str] = {
    "r": "R",
    "c": "C",
    "l": "L",
    "v": "V",
    "i": "I",
    "d": "D",
    "q": "Q_NPN",   # default; refine by model name
    "m": "M_NMOS",  # default
    "e": "E",
    "f": "F",
    "g": "G",
    "h": "H",
    "t": "T",
    "k": "T",        # mutual inductance — approximate as transformer
    "s": "SW",
    "w": "SW",
    "b": "V",        # behavioural source — treat as V
    "j": "D",        # JFET — approximate as diode for display
    "x": "R",        # subcircuit — generic block
    "u": "R",
}

_VALUE_RE = re.compile(
    r"^([0-9]+\.?[0-9]*|[0-9]*\.[0-9]+)"
    r"([eE][+-]?[0-9]+)?([TGMkKmuUnpPf]?)$",
    re.IGNORECASE,
)


def _parse_params(tokens: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for tok in tokens:
        if "=" in tok:
            k, _, v = tok.partition("=")
            params[k.strip()] = v.strip()
    return params


def parse_netlist(text: str) -> list[dict[str, Any]]:
    """Parse a SPICE netlist and return a list of component dicts."""
    components: list[dict[str, Any]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("*") or line.startswith(";"):
            continue
        if line.startswith(".") or line.startswith("+"):
            continue

        tokens = line.split()
        if not tokens:
            continue

        ref = tokens[0]
        ch = ref[0].lower()
        comp_type = _FIRST_CHAR_MAP.get(ch, "R")

        # Heuristic: PNP/NPN from model name
        if ch == "q" and len(tokens) >= 5:
            model = tokens[4].lower()
            if "pnp" in model or "p2n" in model:
                comp_type = "Q_PNP"

        # Heuristic: PMOS from model name
        if ch == "m" and len(tokens) >= 7:
            model = tokens[6].lower()
            if "pmos" in model or "p-ch" in model:
                comp_type = "M_PMOS"

        non_param = [t for t in tokens[1:] if "=" not in t]
        param_tokens = [t for t in tokens[1:] if "=" in t]

        nodes: list[str] = []
        value = ""
        if non_param:
            nodes = non_param[:-1]
            value = non_param[-1]

        params = _parse_params(param_tokens)

        components.append({
            "type": comp_type,
            "ref": ref,
            "nodes": nodes,
            "value": value,
            "params": params,
        })

    return components


def layout_components(
    components: list[dict[str, Any]],
    cols: int = 6,
    col_spacing: int = 160,
    row_spacing: int = 120,
    origin_x: int = -480,
    origin_y: int = -360,
) -> list[tuple[float, float]]:
    """Assign grid positions to parsed components."""
    positions: list[tuple[float, float]] = []
    for i in range(len(components)):
        col = i % cols
        row = i // cols
        x = origin_x + col * col_spacing
        y = origin_y + row * row_spacing
        positions.append((float(x), float(y)))
    return positions
