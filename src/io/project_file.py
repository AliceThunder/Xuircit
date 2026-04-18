"""Project file I/O: save/load .xcit JSON files."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..models.circuit import Circuit

_VERSION = "1.0"


def save_project(circuit: Circuit, filepath: str) -> None:
    """Serialize circuit to a JSON .xcit file."""
    data = {
        "version": _VERSION,
        "created": datetime.now(timezone.utc).isoformat(),
        "components": circuit.components,
        "wires": circuit.wires,
    }
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def load_project(filepath: str) -> Circuit:
    """Deserialize a .xcit file and return a populated Circuit."""
    with open(filepath, encoding="utf-8") as fh:
        data = json.load(fh)
    circuit = Circuit()
    circuit.from_dict(data)
    return circuit
