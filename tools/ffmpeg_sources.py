"""Bindet ffmpeg-Binaerdateien, Quellen und Originalhinweise an feste Hashes."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import runpy
import shutil
import tempfile
from urllib.request import Request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "installer" / "ffmpeg-lock.json"
SOURCES = ROOT / "bin" / "sources" / "ffmpeg"
HOSTS = frozenset({
    "ffmpeg.org", "www.ffmpeg.org", "www.gyan.dev", "gyan.dev", "github.com",
    "codeload.github.com", "raw.githubusercontent.com",
    "release-assets.githubusercontent.com", "objects.githubusercontent.com",
    "downloads.xvid.com",
})


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked_path(base: Path, name: str) -> Path:
    target = (base / name).resolve()
    if not target.is_relative_to(base.resolve()) or target == base.resolve():
        raise ValueError("Ungueltiger Pfad im Quellenmanifest: " + name)
    return target


def valid(path: Path, entry: dict) -> bool:
    return (path.is_file() and path.stat().st_size == entry["bytes"]
            and sha256(path) == entry["sha256"])


def download(entry: dict, target: Path) -> None:
    # Kein automatisches Aktualisieren: URL, Groesse und Hash sind fest.
    transport = runpy.run_path(str(ROOT / "src/fevdl/core/transport.py"))
    request = Request(entry["url"], headers={"User-Agent": "FevDownload-Quellen"})
    with transport["open_https"](request, 90, HOSTS) as response, target.open("xb") as output:
        remaining = entry["bytes"]
        while chunk := response.read(min(1024 * 1024, remaining + 1)):
            remaining -= len(chunk)
            if remaining < 0:
                raise ValueError("Download groesser als erwartet: " + entry["url"])
            output.write(chunk)
    if not valid(target, entry):
        raise ValueError("Quellen-Download: Groesse oder SHA-256 stimmt nicht: " + entry["url"])


def prepare(lock: dict, bootstrap: bool) -> None:
    SOURCES.mkdir(parents=True, exist_ok=True)
    need_binary = []
    for name, entry in lock["binaries"].items():
        target = checked_path(ROOT / "bin", name)
        if target.exists() and not valid(target, entry):
            raise ValueError("Unbekannter ffmpeg-Build in bin/: " + name
                             + ". Quellenmanifest bewusst aktualisieren; nichts wurde ersetzt.")
        if not target.exists():
            need_binary.append(name)
    if need_binary and not bootstrap:
        raise ValueError("ffmpeg fehlt. setup.ps1 ausfuehren.")
    with tempfile.TemporaryDirectory(prefix="fevdl-quellen-") as temporary:
        work = Path(temporary)
        members = [e for e in lock["files"] if "member" in e
                   and not valid(checked_path(SOURCES, e["path"]), e)]
        if need_binary or members:
            archive = work / "gyan.zip"
            download(lock["binary_archive"], archive)
            with zipfile.ZipFile(archive) as source:
                for entry in members:
                    target = checked_path(SOURCES, entry["path"])
                    staged = work / target.name
                    # Nur feste Manifest-Mitglieder lesen, niemals extractall.
                    with source.open(entry["member"]) as input_file, staged.open("xb") as output:
                        shutil.copyfileobj(input_file, output)
                    if not valid(staged, entry):
                        raise ValueError("Falscher Originalhinweis: " + entry["path"])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(staged, target)
                for name in need_binary:
                    entry = lock["binaries"][name]
                    staged = work / name
                    with source.open(lock["binary_prefix"] + name) as input_file, staged.open("xb") as output:
                        shutil.copyfileobj(input_file, output)
                    if not valid(staged, entry):
                        raise ValueError("Falsche Binaerdatei im gyan-Archiv: " + name)
                    os.replace(staged, checked_path(ROOT / "bin", name))
        for entry in lock["files"]:
            target = checked_path(SOURCES, entry["path"])
            if valid(target, entry):
                continue
            if "member" in entry:
                raise ValueError("Originalhinweis fehlt: " + entry["path"])
            staged = work / target.name
            print("Lade Quelle: " + entry["path"], flush=True)
            download(entry, staged)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, target)


def check(lock: dict) -> None:
    for name, version in lock["notice_package_versions"].items():
        if metadata.version(name) != version:
            raise ValueError("Lizenzhinweise passen nicht zur Paketfassung: " + name
                             + ". Quellen und Hinweise bewusst aktualisieren.")
    for name, entry in lock["binaries"].items():
        if not valid(checked_path(ROOT / "bin", name), entry):
            raise ValueError("Binaerdatei fehlt oder passt nicht zum Quellenpaket: " + name)
    for entry in lock["files"]:
        if not valid(checked_path(SOURCES, entry["path"]), entry):
            raise ValueError("Quelle/Lizenz fehlt oder Hash falsch: " + entry["path"]
                             + ". setup.ps1 -NurFfmpeg ausfuehren.")
    for name in lock["required_notices"]:
        path = checked_path(ROOT / "installer/licenses", name)
        if not path.is_file() or not path.stat().st_size:
            raise ValueError("Lizenzhinweis fehlt: " + name)
    provenance = json.loads((ROOT / "installer/licenses/HERKUNFT.json").read_text(encoding="utf-8"))
    for entry in provenance:
        path = checked_path(ROOT / "installer/licenses", entry["path"])
        if not path.is_file() or sha256(path) != entry["sha256"]:
            raise ValueError("Original-Lizenzhinweis fehlt oder wurde veraendert: " + entry["path"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--download", action="store_true")
    action.add_argument("--check", action="store_true")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--copy-to", type=Path)
    args = parser.parse_args()
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    if args.download:
        prepare(lock, args.bootstrap)
    check(lock)
    if args.copy_to:
        target = args.copy_to / "ffmpeg"
        target.mkdir(parents=True, exist_ok=True)
        for entry in lock["files"]:
            destination = checked_path(target, entry["path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(checked_path(SOURCES, entry["path"]), destination)
        shutil.copyfile(LOCK, target / LOCK.name)
    print("ffmpeg 9.0: Binaerdateien, Quellen und Hinweise SHA-256-geprueft.")
    print("Offen: vollstaendige Bibliotheksquellen/Build-Skripte und Qt/curl-Abgleich; siehe LIZENZEN.txt.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        raise SystemExit("ffmpeg-Quellenpruefung: " + str(error))
