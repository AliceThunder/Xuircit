"""SPICE netlist generator — converts Circuit model to netlist text."""
from __future__ import annotations

from datetime import datetime, timezone

from ..models.circuit import Circuit

# Map type_name → SPICE element-line prefix
_TYPE_PREFIX: dict[str, str] = {
    "R": "R", "C": "C", "L": "L", "T": "T",
    "V": "V", "I": "I", "E": "E", "F": "F", "G": "G", "H": "H",
    "D": "D", "Z": "D",
    "Q_NPN": "Q", "Q_PNP": "Q",
    "M_NMOS": "M", "M_PMOS": "M",
    "IGBT": "Q",
    "SW": "S", "SCR": "X", "TRIAC": "X",
    "GND": "", "NETLABEL": "", "JUNCTION": "",
}

_DEFAULT_NODES: dict[str, list[str]] = {
    "R":      ["N001", "N002"],
    "C":      ["N001", "N002"],
    "L":      ["N001", "N002"],
    "T":      ["N001", "N002", "N003", "N004"],
    "V":      ["N001", "0"],
    "I":      ["N001", "0"],
    "E":      ["N001", "0", "N002", "0"],
    "F":      ["N001", "0", "VSRC", "1"],
    "G":      ["N001", "0", "N002", "0"],
    "H":      ["N001", "0", "VSRC", "1"],
    "D":      ["ANODE", "CATHODE"],
    "Z":      ["ANODE", "CATHODE"],
    "Q_NPN":  ["COLLECTOR", "BASE", "EMITTER"],
    "Q_PNP":  ["COLLECTOR", "BASE", "EMITTER"],
    "M_NMOS": ["DRAIN", "GATE", "SOURCE", "BODY"],
    "M_PMOS": ["DRAIN", "GATE", "SOURCE", "BODY"],
    "IGBT":   ["COLLECTOR", "GATE", "EMITTER"],
    "SW":     ["N001", "N002"],
    "SCR":    ["ANODE", "CATHODE", "GATE"],
    "TRIAC":  ["MT1", "MT2", "GATE"],
}


def _build_net_map(circuit: Circuit) -> dict[tuple[str, str], str]:
    net_map: dict[tuple[str, str], str] = {}
    net_counter = 1
    for wire in circuit.wires:
        name = wire.get("net_name", "")
        if not name:
            name = f"N{net_counter:03d}"
            net_counter += 1
        sp = wire.get("start_pin")
        ep = wire.get("end_pin")
        if sp:
            net_map[(sp[0], sp[1])] = name
        if ep:
            net_map[(ep[0], ep[1])] = name
    return net_map


def generate_netlist(circuit: Circuit) -> str:
    """Generate a SPICE netlist string from the circuit model."""
    lines: list[str] = []
    lines.append("* Xuircit schematic netlist")
    lines.append(
        f"* Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    lines.append("")

    net_map = _build_net_map(circuit)

    from ..models.component_library import ComponentLibrary
    lib = ComponentLibrary()

    for comp in circuit.components:
        ctype = comp.get("type", "R")
        prefix = _TYPE_PREFIX.get(ctype, "X")
        if not prefix:
            continue

        ref = comp.get("ref", "X1")
        value = comp.get("value", "1")
        params = comp.get("params", {})
        comp_id = comp.get("id", "")

        cdef = lib.get(ctype)
        pin_names = cdef.pins if cdef else []

        node_tokens: list[str] = []
        for pin in pin_names:
            key = (comp_id, pin)
            node_tokens.append(net_map.get(key, pin.upper()))

        if not node_tokens:
            node_tokens = _DEFAULT_NODES.get(ctype, ["N001", "N002"])

        token_str = " ".join(node_tokens)
        param_str = " ".join(f"{k}={v}" for k, v in params.items())
        parts = [ref, token_str, value]
        if param_str:
            parts.append(param_str)
        lines.append(" ".join(parts))

    lines.append("")
    lines.append(".end")
    return "\n".join(lines)
