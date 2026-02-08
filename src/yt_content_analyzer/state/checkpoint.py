from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any

@dataclass
class CheckpointStore:
    path: Path

    def init_if_missing(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({"UNITS": {}}, indent=2), encoding="utf-8")

    def load(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def is_done(self, unit_key: str, stage: str) -> bool:
        data = self.load()
        return data.get("UNITS", {}).get(unit_key, {}).get(stage) == "DONE"

    def mark(self, unit_key: str, stage: str, status: str = "DONE") -> None:
        data = self.load()
        units = data.setdefault("UNITS", {})
        units.setdefault(unit_key, {})
        units[unit_key][stage] = status
        self.save(data)
