"""Append-only persistence for derived snapshots and briefs."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .brief import CEOBrief
from .models import CompanyStateSnapshot, DashboardError


class DashboardStore:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir).resolve()

    def put_snapshot(self, snapshot: CompanyStateSnapshot) -> Path:
        return self._put(self.output_dir / "snapshots" / f"{snapshot.snapshot_id}.json",
                         snapshot.canonical_json().encode("utf-8"))

    def put_brief(self, brief: CEOBrief) -> Path:
        return self._put(self.output_dir / "briefs" / f"{brief.snapshot_id}.txt",
                         brief.render_text().encode("utf-8"))

    def get_snapshot(self, snapshot_id: str) -> CompanyStateSnapshot:
        path = self.output_dir / "snapshots" / f"{snapshot_id}.json"
        if not path.is_file():
            raise DashboardError(f"no dashboard snapshot {snapshot_id!r}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return CompanyStateSnapshot.from_dict(data)

    @staticmethod
    def load_path(path: str | Path) -> CompanyStateSnapshot:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return CompanyStateSnapshot.from_dict(data)

    @staticmethod
    def _put(path: Path, payload: bytes) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0))
        except FileExistsError:
            if path.read_bytes() == payload:
                return path
            raise DashboardError(f"refusing to overwrite differing derived output {path}") from None
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise DashboardError(f"short write while creating derived output {path}")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return path
