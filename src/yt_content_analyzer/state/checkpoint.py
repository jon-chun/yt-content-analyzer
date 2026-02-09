from __future__ import annotations
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


@dataclass
class CheckpointStore:
    path: Path

    def init_if_missing(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({"UNITS": {}}, indent=2), encoding="utf-8")

    def load(self) -> dict[str, Any]:
        try:
            result: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
            return result
        except (json.JSONDecodeError, UnicodeDecodeError):
            backup = self.path.with_suffix(".json.corrupt")
            shutil.copy2(self.path, backup)
            _logger.warning(
                "Corrupt checkpoint %s — backed up to %s, reinitializing", self.path, backup
            )
            data: dict[str, Any] = {"UNITS": {}}
            self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return data

    def save(self, data: dict[str, Any]) -> None:
        content = json.dumps(data, indent=2).encode("utf-8")
        fd = None
        tmp_path = None
        try:
            fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent))
            tmp_path = Path(tmp_name)
            os.write(fd, content)
            os.close(fd)
            fd = None
            tmp_path.replace(self.path)
        except BaseException:
            if fd is not None:
                os.close(fd)
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink()
            raise

    def is_done(self, unit_key: str, stage: str) -> bool:
        data = self.load()
        status: str | None = data.get("UNITS", {}).get(unit_key, {}).get(stage)
        return status == "DONE"

    def mark(self, unit_key: str, stage: str, status: str = "DONE") -> None:
        data = self.load()
        units = data.setdefault("UNITS", {})
        units.setdefault(unit_key, {})
        units[unit_key][stage] = status
        self.save(data)
