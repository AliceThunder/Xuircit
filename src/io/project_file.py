"""Project file I/O: save/load .xcit JSON files."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..models.circuit import Circuit

_VERSION = "1.1"


def save_project(circuit: Circuit, filepath: str) -> None:
    """Serialize circuit to a JSON .xcit file.

    Wires are NOT saved — they are regenerated automatically when the
    project is loaded.  Each component entry includes a ``library_id``
    field so the correct library can be looked up on load.
    """
    data = {
        "version": _VERSION,
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
    circuit.from_dict(data)
    return circuit
