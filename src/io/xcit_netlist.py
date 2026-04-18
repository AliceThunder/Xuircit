"""XCIT extended netlist format — SPICE netlist with embedded position data.

Format overview
---------------
The XCIT format extends a standard SPICE netlist with two optional sections:

  .xcit_layout
      One line per SPICE component:
      ``ref  x  y  rotation  flip_h  flip_v  library_id
        label_ref_dx  label_ref_dy  label_val_dx  label_val_dy``
  .end_xcit_layout

  .xcit_virtual
      One line per non-SPICE component (GND, ELBOW, TEE, NETLABEL, JUNCTION):
      ``type_name  ref  x  y  rotation  flip_h  flip_v  library_id``
  .end_xcit_virtual

Both sections are placed before the ``.end`` directive.  A standard SPICE
simulator will reject the section headers as unknown directives but will
otherwise ignore them.

Wires are NOT saved — they are automatically redrawn when the netlist is
loaded.  Stripping the sections with :func:`strip_positions` yields a
valid SPICE netlist.
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

# Non-SPICE component types that should be saved in .xcit_virtual
_VIRTUAL_TYPES: frozenset[str] = frozenset({
    "GND", "NETLABEL", "JUNCTION", "ELBOW", "TEE",
})

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

    The output is a valid SPICE netlist with an embedded ``.xcit_layout``
    section that records each component's position, rotation, flip state,
    and library reference.  Non-SPICE components (ELBOW, TEE, GND, etc.)
    are recorded in a ``.xcit_virtual`` section (Issue 5).

    Wire data is NOT included — wires are auto-generated on load.
    """
    lines: list[str] = []
    lines.append("* Xuircit Extended Netlist (XCIT)")
    lines.append(
        f"* Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    lines.append("* Strip .xcit_layout section for standard SPICE.")
    lines.append("* XCIT_LABEL_FORMAT 2")
    lines.append("")

    net_map = _build_net_map(circuit)

    from ..models.library_system import LibraryManager
    lm = LibraryManager()

    # ── SPICE element lines ──────────────────────────────────────────────
    for comp in circuit.components:
        ctype = comp.get("type", "R")
        prefix = _TYPE_PREFIX.get(ctype, "X")
        if not prefix:
            continue  # non-SPICE; handled in .xcit_virtual

        ref = comp.get("ref", "X1")
        value = comp.get("value", "1")
        params = comp.get("params", {})
        comp_id = comp.get("id", "")
        lib_id = comp.get("library_id")

        result = lm.find_entry(ctype, lib_id)
        pin_names: list[str] = []
        if result is not None:
            entry, _ = result
            pin_names = entry.pin_names if entry.is_builtin else [
                p.get("name", "") for p in entry.pins
            ]

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

    # ── Layout section (SPICE components) ───────────────────────────────
    lines.append(".xcit_layout")
    lines.append(
        "* ref  x  y  rotation  flip_h  flip_v  library_id"
        "  label_ref_dx  label_ref_dy  label_val_dx  label_val_dy"
    )
    for comp in circuit.components:
        ctype = comp.get("type", "R")
        if ctype in _VIRTUAL_TYPES:
            continue  # non-SPICE handled below
        ref = comp.get("ref", "X1")
        x = comp.get("x", 0.0)
        y = comp.get("y", 0.0)
        rot = comp.get("rotation", 0)
        fh = 1 if comp.get("flip_h", False) else 0
        fv = 1 if comp.get("flip_v", False) else 0
        lib_id = comp.get("library_id") or "preset"
        lrp = comp.get("label_ref_pos", [0.0, -22.0])
        lvp = comp.get("label_val_pos", [0.0, 14.0])
        lines.append(
            f"{ref}  {x:.2f}  {y:.2f}  {rot}  {fh}  {fv}  {lib_id}"
            f"  {lrp[0]:.2f}  {lrp[1]:.2f}  {lvp[0]:.2f}  {lvp[1]:.2f}"
        )
    lines.append(".end_xcit_layout")
    lines.append("")

    # ── Virtual section (non-SPICE components: ELBOW, TEE, GND …) ────────
    virtual_comps = [c for c in circuit.components
                     if c.get("type", "") in _VIRTUAL_TYPES]
    if virtual_comps:
        lines.append(".xcit_virtual")
        lines.append("* type_name  ref  x  y  rotation  flip_h  flip_v  library_id")
        for comp in virtual_comps:
            ctype = comp.get("type", "ELBOW")
            ref = comp.get("ref", "V?")
            x = comp.get("x", 0.0)
            y = comp.get("y", 0.0)
            rot = comp.get("rotation", 0)
            fh = 1 if comp.get("flip_h", False) else 0
            fv = 1 if comp.get("flip_v", False) else 0
            lib_id = comp.get("library_id") or "preset"
            lines.append(
                f"{ctype}  {ref}  {x:.2f}  {y:.2f}  {rot}  {fh}  {fv}  {lib_id}"
            )
        lines.append(".end_xcit_virtual")
        lines.append("")

    lines.append(".end")
    return "\n".join(lines)


def strip_positions(xcit_text: str) -> str:
    """Remove the .xcit_layout and .xcit_virtual sections from an XCIT netlist.

    Returns a standard SPICE netlist string that any simulator can parse.
    """
    in_section = False
    result: list[str] = []
    for line in xcit_text.splitlines():
        stripped = line.strip().lower()
        if stripped in (".xcit_layout", ".xcit_wires", ".xcit_virtual"):
            in_section = True
            continue
        if stripped in (".end_xcit_layout", ".end_xcit_wires", ".end_xcit_virtual"):
            in_section = False
            continue
        if not in_section:
            result.append(line)
    text = "\n".join(result)
    text = text.replace(
        "* Xuircit Extended Netlist (XCIT)",
        "* Xuircit schematic netlist",
    )
    text = text.replace(
        "* Strip .xcit_layout section for standard SPICE.\n",
        "",
    )
    return text


def parse_xcit_netlist(
    text: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]], int]:
    """Parse an XCIT netlist.

    Returns a 4-tuple:
    - ``components``: list of SPICE component dicts
    - ``positions``: mapping ref → position dict
      ``{x, y, rotation, flip_h, flip_v, library_id, label_ref_pos, label_val_pos}``
    - ``virtual_comps``: list of non-SPICE component dicts (ELBOW, TEE, GND, …)
    - ``label_format``: integer (1 = old screen-space, 2 = parent-local)

    Wire data is not returned — wires are auto-generated on rebuild.
    """
    from ..io.netlist_parser import parse_netlist

    spice_lines: list[str] = []
    layout_lines: list[str] = []
    virtual_lines: list[str] = []
    label_format = 1  # assume old format unless the file says otherwise
    state = "spice"

    for line in text.splitlines():
        raw_stripped = line.strip()
        stripped = raw_stripped.lower()
        # Check for label format comment (must test raw line, not lowercased)
        if raw_stripped.startswith("* XCIT_LABEL_FORMAT"):
            try:
                label_format = int(raw_stripped.split()[-1])
            except (ValueError, IndexError):
                pass
            continue
        if stripped in (".xcit_layout",):
            state = "layout"
            continue
        if stripped in (".end_xcit_layout",):
            state = "spice"
            continue
        if stripped in (".xcit_virtual",):
            state = "virtual"
            continue
        if stripped in (".end_xcit_virtual",):
            state = "spice"
            continue
        # Skip legacy wire sections silently
        if stripped in (".xcit_wires",):
            state = "skip"
            continue
        if stripped in (".end_xcit_wires",):
            state = "spice"
            continue
        if state == "spice":
            spice_lines.append(line)
        elif state == "layout":
            layout_lines.append(line)
        elif state == "virtual":
            virtual_lines.append(line)

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
            # library_id is in field 6 (new format) — optional
            idx = 6
            lib_id: str | None = None
            if len(parts) > idx and not _is_float(parts[idx]):
                lib_id = parts[idx]
                idx += 1
            lrp = [float(parts[idx]), float(parts[idx + 1])] \
                if len(parts) >= idx + 2 else [0.0, -22.0]
            lvp = [float(parts[idx + 2]), float(parts[idx + 3])] \
                if len(parts) >= idx + 4 else [0.0, 14.0]
        except (ValueError, IndexError):
            continue
        positions[ref] = {
            "x": x, "y": y,
            "rotation": rot,
            "flip_h": fh,
            "flip_v": fv,
            "library_id": lib_id,
            "label_ref_pos": lrp,
            "label_val_pos": lvp,
        }

    # Parse .xcit_virtual section (Issue 5)
    virtual_comps: list[dict[str, Any]] = []
    for line in virtual_lines:
        line = line.strip()
        if not line or line.startswith("*"):
            continue
        parts = line.split()
        # format: type_name  ref  x  y  rotation  flip_h  flip_v  [library_id]
        if len(parts) < 7:
            continue
        try:
            vtype = parts[0]
            vref = parts[1]
            vx, vy = float(parts[2]), float(parts[3])
            vrot = float(parts[4])
            vfh = bool(int(parts[5]))
            vfv = bool(int(parts[6]))
            vlib = parts[7] if len(parts) > 7 else "preset"
        except (ValueError, IndexError):
            continue
        virtual_comps.append({
            "type": vtype,
            "ref": vref,
            "x": vx,
            "y": vy,
            "rotation": vrot,
            "flip_h": vfh,
            "flip_v": vfv,
            "library_id": vlib,
        })

    return components, positions, virtual_comps, label_format


def _is_float(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False

