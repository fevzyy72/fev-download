"""Datenaustausch zwischen dem Resolve-Script und dieser Oberflaeche.

Warum ueber Dateien und nicht direkt? Die kostenlose Version von DaVinci
Resolve laesst seit Version 19.1 kein Scripting von aussen mehr zu. Nur ein
Script, das Resolve selbst startet (Workspace -> Scripts), erreicht die
Schnittstelle. Dieses Script startet die Oberflaeche als eigenes Programm -
und beide verstaendigen sich ueber zwei kleine JSON-Dateien:

    job.json     schreibt das Resolve-Script beim Start
    result.json  schreibt die Oberflaeche nach jedem fertigen Download

Das Resolve-Script schaut regelmaessig in result.json und holt neu
hinzugekommene Dateien in den Media Pool. So lassen sich in einer Sitzung auch
mehrere Clips nacheinander laden.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class Job:
    """Was das Resolve-Script der Oberflaeche mitgibt."""

    job_id: str
    project: str = ""
    output_dir: Optional[Path] = None
    resolve_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "project": self.project,
            "output_dir": str(self.output_dir) if self.output_dir else "",
            "resolve_version": self.resolve_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        output_dir = data.get("output_dir") or ""
        return cls(
            job_id=str(data.get("job_id") or ""),
            project=str(data.get("project") or ""),
            output_dir=Path(output_dir) if output_dir else None,
            resolve_version=str(data.get("resolve_version") or ""),
        )


def new_job_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"


def write_json(path: Path, data: dict[str, Any]) -> None:
    """
    Schreibt erst in eine Nebendatei und benennt sie dann um.

    Sonst koennte die Gegenseite eine halb geschriebene Datei lesen - beide
    Programme laufen gleichzeitig und lesen im Sekundentakt.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def read_json(path: Path) -> Optional[dict[str, Any]]:
    """
    Liest eine JSON-Datei; gibt None zurueck, wenn sie fehlt oder kaputt ist.

    'utf-8-sig' statt 'utf-8': Von PowerShell geschriebene Dateien beginnen oft
    mit einer Byte-Reihenfolge-Marke, an der ein reiner utf-8-Leser scheitert.
    Fehlt die Marke, verhaelt sich utf-8-sig identisch.
    """
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def read_job(path: Path) -> Optional[Job]:
    data = read_json(path)
    if not data or not isinstance(data.get("job_id"), str) or not data["job_id"]:
        return None
    if not isinstance(data.get("output_dir", ""), str):
        return None
    try:
        return Job.from_dict(data)
    except (TypeError, ValueError):
        return None


def write_job(path: Path, job: Job) -> None:
    write_json(path, job.to_dict())


@dataclass
class ResultWriter:
    """Sammelt die fertigen Dateien und meldet sie an das Resolve-Script."""

    path: Path
    job_id: str
    files: list[str] = field(default_factory=list)
    status: str = "running"
    message: str = ""

    def add_file(self, file_path: Path) -> None:
        text = str(file_path)
        if text not in self.files:
            self.files.append(text)
        self._flush()

    def mark_finished(self, status: str = "ok", message: str = "") -> None:
        self.status = status
        self.message = message
        self._flush()

    def _flush(self) -> None:
        write_json(
            self.path,
            {
                "job_id": self.job_id,
                "status": self.status,
                "files": self.files,
                "message": self.message,
                "updated": time.time(),
            },
        )
