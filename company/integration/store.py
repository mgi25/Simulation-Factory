"""Append-only persistence for derived readiness reports, in a caller's directory.

No database and no default location. The caller says where reports go, the
same way every other Company OS store works, so a gate run in a test, in a
worktree and on a reviewer's machine cannot collide.

The write is `O_CREAT | O_EXCL`, which makes "does this already exist" and "may
I create it" one atomic question rather than two racing ones. An identical
re-write is accepted and returns the existing path - re-running the gate twice
on the same day over an unchanged tree is an honest thing to do and should not
be an error. A *differing* write under the same report id is refused, because
two different answers filed under one identity means the stored history no
longer says what was concluded.

A report id contains the fingerprint of its own content, so in practice a
differing write under the same id only happens when an id has been built by
hand. The refusal is still here: an invariant that is currently unreachable by
accident is exactly the one worth enforcing before somebody makes it reachable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .errors import ReportStoreError
from .model import ProductionIntegrationReadinessReport


class ReadinessReportStore:
    """Derived readiness reports under a caller-supplied output directory."""

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir).resolve()

    def path_for(self, report_id: str) -> Path:
        return self.output_dir / "readiness" / f"{report_id}.json"

    def put(self, report: ProductionIntegrationReadinessReport) -> Path:
        """Write the report. Idempotent for identical content, refuses a rewrite."""
        return self._put(
            self.path_for(report.report_id), report.canonical_json().encode("utf-8")
        )

    def put_text(self, report_id: str, text: str) -> Path:
        return self._put(self.output_dir / "readiness" / f"{report_id}.txt", text.encode("utf-8"))

    def get(self, report_id: str) -> dict:
        path = self.path_for(report_id)
        if not path.is_file():
            raise ReportStoreError(f"no readiness report {report_id!r} in {self.output_dir}")
        return json.loads(path.read_text(encoding="utf-8"))

    def ids(self) -> tuple[str, ...]:
        directory = self.output_dir / "readiness"
        if not directory.is_dir():
            return ()
        return tuple(sorted(path.stem for path in directory.glob("*.json")))

    @staticmethod
    def _put(path: Path, payload: bytes) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
            )
        except FileExistsError:
            if path.read_bytes() == payload:
                return path
            raise ReportStoreError(
                f"refusing to overwrite {path} with different content. A readiness "
                "report is what was concluded at one moment; a second, different "
                "conclusion is a new report, not an edit of the old one."
            ) from None
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise ReportStoreError(f"short write while creating {path}")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return path


__all__ = ["ReadinessReportStore"]
