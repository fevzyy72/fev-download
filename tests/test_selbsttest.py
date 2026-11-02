"""
Der Selbsttest (FevDownload.exe --selbsttest) laeuft im Quelltext durch.

Er ist dasselbe Werkzeug, mit dem das gepackte Programm geprueft wird - dieser
Test sorgt dafuer, dass es selbst nicht kaputtgeht. Mit Netz.
"""

import os
import subprocess
import sys

from fevdl import paths

result = subprocess.run(
    [sys.executable, "-m", "fevdl", "--selbsttest"],
    capture_output=True, text=True, timeout=300,
    env={**os.environ, "PYTHONPATH": str(paths.PROJECT_ROOT / "src")},
)

report = paths.IPC_DIR / "selbsttest.txt"
text = report.read_text(encoding="utf-8") if report.is_file() else "(kein Bericht)"
print(text)

assert result.returncode == 0, "Selbsttest meldet Fehler (Exit {})".format(result.returncode)
assert "ERGEBNIS: alles in Ordnung" in text, "Bericht meldet keinen Erfolg"
assert "Ausschnitt" in text and "Vorschaudatei" in text, "Bericht ist unvollstaendig"

print("SELBSTTEST-TEST OK")
