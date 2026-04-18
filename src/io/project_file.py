"""Project file I/O: save/load .xcit JSON files."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..models.circuit import Circuit

_VERSION = "2.0"
# Label position format version:
#   1 = pre-2.0: label offsets were manually rotated (screen-space).
#   2 = 2.0+:    label offsets are in parent-local space (rotation-invariant).
_LABEL_FORMAT = 2


def save_project(circuit: Circuit, filepath: str) -> None:
    """Serialize circuit to a JSON .xcit file.

    Wires are NOT saved — they are regenerated automatically when the
    project is loaded.  Each component entry includes a ``library_id``
    field so the correct library can be looked up on load.
    """
    data = {
        "version": _VERSION,
        "label_format": _LABEL_FORMAT,
        "created": datetime.now(timezone.utc).isoformat(),
        "components": circuit.components,
        # Wires are intentionally omitted; they are auto-drawn on load.
    }
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def load_project(filepath: str) -> Circuit:
    """Deserialize a .xcit file and return a populated Circuit.

    Wire data (if present in older files) is silently ignored because
    wires are regenerated automatically by the scene.
    """
    with open(filepath, encoding="utf-8") as fh:
        data = json.load(fh)
    circuit = Circuit()
    # Set label format so scene can migrate old-format label positions.
    circuit.label_format = int(data.get("label_format", 1))
    circuit.from_dict(data)
    return circuit
