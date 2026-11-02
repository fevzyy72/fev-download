# -*- mode: python ; coding: utf-8 -*-
"""Bauplan fuer PyInstaller - erzeugt dist/FevDownload/FevDownload.exe.

Aufruf ueber build_installer.ps1, nicht direkt.

Das Ergebnis ist ein Ordner (nicht eine einzelne Datei). Absicht: Eine
zusammengepackte .exe entpackt sich bei jedem Start in einen Temp-Ordner, was
mehrere Sekunden kostet und Virenscanner reizt. Verteilt wird ohnehin ueber den
Installer, also sieht niemand den Ordner.

bin/ und assets/ kommen NICHT hier hinein, sondern legt der Installer neben die
.exe - paths.PROJECT_ROOT zeigt im gepackten Zustand genau dorthin. Die 196 MB
ffmpeg durch PyInstaller zu schleusen waere nur Umweg und Bauzeit.
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

# yt-dlp sucht seine Extraktoren zur Laufzeit ueber importlib zusammen. PyInstaller
# sieht davon nichts, weil kein import im Quelltext steht - ohne diese Zeile
# kennt das fertige Programm keine einzige Plattform.
hidden = collect_submodules("yt_dlp.extractor")
# Auch die Netzwerk-Handler werden dynamisch eingebunden. curl_cffi braucht
# ausser seinem Python-Code die native libcurl-DLL und die TLS-Zertifikate.
hidden += collect_submodules("yt_dlp.networking")
curl_data, curl_binaries, curl_hidden = collect_all("curl_cffi")
hidden += curl_hidden + ["_cffi_backend", "certifi"]
# Die Metadaten (.dist-info) von yt-dlp: Beim Start muss sich die mitgelieferte
# Fassung erfragen lassen, OHNE das Paket einzubinden (paths.bundled_ytdlp_version),
# sonst laesst sich nicht entscheiden, ob eine nachgeladene Fassung neuer ist.
yt_dlp_metadata = copy_metadata("yt-dlp")

# PySide6 bringt weit mehr mit, als hier gebraucht wird. Der Code bindet nur
# QtCore, QtGui, QtWidgets, QtMultimedia und QtMultimediaWidgets ein - alles
# andere ist Ballast. Vor allem QtWebEngine faellt ins Gewicht (~150 MB).
excluded_qt = [
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtNfc",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialBus",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtXml",
]

# Grosse Bibliotheken, die niemand anfordert, die aber ueber Umwege
# hereingezogen werden, wenn sie zufaellig in der Umgebung liegen.
excluded_other = [
    "tkinter",
    "unittest",
    "pydoc_data",
    "numpy",
    "PIL",
    "setuptools",
    "pip",
]

analysis = Analysis(
    ["launch.pyw"],
    pathex=["src"],
    binaries=curl_binaries,
    datas=curl_data + yt_dlp_metadata,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=excluded_qt + excluded_other,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="FevDownload",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Kein Konsolenfenster - wie launch.pyw es bisher ueber pythonw.exe geloest hat.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets\\fevdl.ico",
)

COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    # UPX aus: Es spart kaum etwas an bereits komprimierten Qt-Dateien, macht
    # aber gepackte .exe-Dateien fuer Virenscanner verdaechtig - und die melden
    # bei einem Downloader ohnehin schon gern Fehlalarm.
    upx=False,
    upx_exclude=[],
    name="FevDownload",
)
