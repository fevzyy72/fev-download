"""Fuehrt eine Testdatei mit eigenen IPC-Dateien und Qt-Einstellungen aus."""

from __future__ import annotations

import json
import os
import runpy
import sys
import tempfile
from pathlib import Path


def main() -> None:
    test_file = Path(sys.argv[1]).resolve()
    project_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="fevdl-tests-") as temporary:
        isolated = Path(temporary)
        os.environ["LOCALAPPDATA"] = str(isolated)
        os.environ["FEVDL_NO_UPDATE_CHECK"] = "1"
        ipc = isolated / "FevDownloader"
        ipc.mkdir()
        (ipc / "install.json").write_text(
            json.dumps({"project_root": str(project_root)}), encoding="utf-8"
        )

        from PySide6 import QtCore

        original_settings = QtCore.QSettings
        for scope in (original_settings.UserScope, original_settings.SystemScope):
            original_settings.setPath(original_settings.IniFormat, scope, str(isolated / "settings"))

        class IsolatedSettings(original_settings):
            def __init__(self, *args, **kwargs):
                # QSettings(org, app) verwendet unter Windows trotz
                # setDefaultFormat weiterhin die echte Benutzer-Registry.
                if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], str):
                    args = (original_settings.IniFormat, original_settings.UserScope, *args)
                super().__init__(*args, **kwargs)

        QtCore.QSettings = IsolatedSettings
        sys.argv = [str(test_file), *sys.argv[2:]]
        sys.path.insert(0, str(test_file.parent))
        runpy.run_path(str(test_file), run_name="__main__")


if __name__ == "__main__":
    main()
