"""XCIT extended netlist format — SPICE netlist with embedded position data.

Format overview
---------------
The XCIT format extends a standard SPICE netlist with two optional sections:

  .xcit_layout
      One line per component: ``ref  x  y  rotation  flip_h  flip_v``
  .end_xcit_layout

  .xcit_wires
      One line per wire:
      ``id  start_x  start_y  end_x  end_y  start_comp  start_pin  end_comp  end_pin  net``
  .end_xcit_wires

Both sections are placed between the last element line and the ``.end``
directive.  A standard SPICE simulator will reject the section headers as
unknown directives but will otherwise ignore them because they begin with ``.``
(most simulators skip unknown directives rather than aborting).

Stripping the two sections with :func:`strip_positions` yields a valid SPICE
netlist that any simulator can use.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ..models.circuit import Circuit

# Map type_name → SPICE element-line prefix (same as netlist_generator.py)
_TYPE_PREFIX: dict[str, str] = {
    "R": "R", "C": "C", "L": "L", "T": "T",
    "V": "V", "I": "I", "E": "E", "F": "F", "G": "G", "H": "H",
    "D": "D", "Z": "D",
    "Q_NPN": "Q", "Q_PNP": "Q",
    "M_NMOS": "M", "M_PMOS": "M",
    "IGBT": "Q",
    "SW": "S", "SCR": "X", "TRIAC": "X",
    "GND": "", "NETLABEL": "", "JUNCTION": "",
    "ELBOW": "", "TEE": "",
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


def generate_xcit_netlist(circuit: Circuit) -> str:
    """Generate an XCIT extended netlist string from the circuit model.

    The output is a valid SPICE netlist with embedded ``.xcit_layout`` and
    ``.xcit_wires`` sections that record each component's position, rotation,
    and flip state, plus every wire's geometry and pin connections.
    """
    lines: list[str] = []
    lines.append("* Xuircit Extended Netlist (XCIT)")
    lines.append(
        f"* Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    lines.append(
        "* Strip .xcit_layout and .xcit_wires sections for standard SPICE."
    )
    lines.append("")

    net_map = _build_net_map(circuit)

    from ..models.component_library import ComponentLibrary
    lib = ComponentLibrary()

    # ── SPICE element lines ──────────────────────────────────────────────
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

    # ── Layout section ───────────────────────────────────────────────────
    lines.append(".xcit_layout")
    lines.append(
        "* ref  x  y  rotation  flip_h  flip_v  label_ref_dx  label_ref_dy"
        "  label_val_dx  label_val_dy"
    )
    for comp in circuit.components:
        ref = comp.get("ref", "X1")
        x = comp.get("x", 0.0)
        y = comp.get("y", 0.0)
        rot = comp.get("rotation", 0)
        fh = 1 if comp.get("flip_h", False) else 0
        fv = 1 if comp.get("flip_v", False) else 0
        lrp = comp.get("label_ref_pos", [0.0, -22.0])
        lvp = comp.get("label_val_pos", [0.0, 14.0])
        lines.append(
            f"{ref}  {x:.2f}  {y:.2f}  {rot}  {fh}  {fv}"
            f"  {lrp[0]:.2f}  {lrp[1]:.2f}  {lvp[0]:.2f}  {lvp[1]:.2f}"
        )
    lines.append(".end_xcit_layout")
    lines.append("")

    # ── Wires section ────────────────────────────────────────────────────
    lines.append(".xcit_wires")
    lines.append(
        "* id  start_x  start_y  end_x  end_y"
        "  start_comp  start_pin  end_comp  end_pin  net"
    )
    for wire in circuit.wires:
        wid = wire.get("id", str(uuid.uuid4()))
        sx, sy = wire.get("start", [0.0, 0.0])
        ex, ey = wire.get("end", [0.0, 0.0])
        sp = wire.get("start_pin") or ["", ""]
        ep = wire.get("end_pin") or ["", ""]
        net = wire.get("net_name", "")
        lines.append(
            f"{wid}  {sx:.2f}  {sy:.2f}  {ex:.2f}  {ey:.2f}"
            f"  {sp[0]}  {sp[1]}  {ep[0]}  {ep[1]}  {net}"
        )
    lines.append(".end_xcit_wires")
    lines.append("")

    lines.append(".end")
    return "\n".join(lines)


def strip_positions(xcit_text: str) -> str:
    """Remove the .xcit_layout and .xcit_wires sections from an XCIT netlist.

    Returns a standard SPICE netlist string that any simulator can parse.
    The first comment line is updated to reflect that positions were stripped.
    """
    in_section = False
    result: list[str] = []
    for line in xcit_text.splitlines():
        stripped = line.strip().lower()
        if stripped in (".xcit_layout", ".xcit_wires"):
            in_section = True
            continue
        if stripped in (".end_xcit_layout", ".end_xcit_wires"):
            in_section = False
            continue
        if not in_section:
            result.append(line)
    # Replace the extended-format header comment if present
    text = "\n".join(result)
    text = text.replace(
        "* Xuircit Extended Netlist (XCIT)",
        "* Xuircit schematic netlist",
    )
    text = text.replace(
        "* Strip .xcit_layout and .xcit_wires sections for standard SPICE.\n",
        "",
    )
    return text


def parse_xcit_netlist(
    text: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Parse an XCIT netlist.

    Returns a 3-tuple:
    - ``components``: list of component dicts (as from netlist_parser.parse_netlist)
    - ``positions``: mapping ref → position dict
      ``{x, y, rotation, flip_h, flip_v, label_ref_pos, label_val_pos}``
    - ``wires``: list of wire dicts
    """
    from ..io.netlist_parser import parse_netlist

    spice_lines: list[str] = []
    layout_lines: list[str] = []
    wire_lines: list[str] = []
    state = "spice"

    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped == ".xcit_layout":
            state = "layout"
            continue
        if stripped == ".end_xcit_layout":
            state = "spice"
            continue
        if stripped == ".xcit_wires":
            state = "wires"
            continue
        if stripped == ".end_xcit_wires":
            state = "spice"
            continue
        if state == "spice":
            spice_lines.append(line)
        elif state == "layout":
            layout_lines.append(line)
        elif state == "wires":
            wire_lines.append(line)

    components = parse_netlist("\n".join(spice_lines))

    positions: dict[str, dict[str, Any]] = {}
    for line in layout_lines:
        line = line.strip()
        if not line or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        ref = parts[0]
        try:
            x, y = float(parts[1]), float(parts[2])
            rot = float(parts[3])
            fh = bool(int(parts[4]))
            fv = bool(int(parts[5]))
            lrp = [float(parts[6]), float(parts[7])] if len(parts) >= 8 else [0.0, -22.0]
            lvp = [float(parts[8]), float(parts[9])] if len(parts) >= 10 else [0.0, 14.0]
        except (ValueError, IndexError):
            continue
        positions[ref] = {
            "x": x, "y": y,
            "rotation": rot,
            "flip_h": fh,
            "flip_v": fv,
            "label_ref_pos": lrp,
            "label_val_pos": lvp,
        }

    wires: list[dict[str, Any]] = []
    for line in wire_lines:
        line = line.strip()
        if not line or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            wid = parts[0]
            sx, sy = float(parts[1]), float(parts[2])
            ex, ey = float(parts[3]), float(parts[4])
            start_comp = parts[5] if len(parts) > 5 else ""
            start_pin = parts[6] if len(parts) > 6 else ""
            end_comp = parts[7] if len(parts) > 7 else ""
            end_pin = parts[8] if len(parts) > 8 else ""
            net = parts[9] if len(parts) > 9 else ""
        except (ValueError, IndexError):
            continue
        wires.append({
            "id": wid,
            "start": [sx, sy],
            "end": [ex, ey],
            "start_pin": [start_comp, start_pin] if start_comp else None,
            "end_pin": [end_comp, end_pin] if end_comp else None,
            "net_name": net,
        })

    return components, positions, wires
