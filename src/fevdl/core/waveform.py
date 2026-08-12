"""Wellenform der Tonspur berechnen.

Vorgehen: ffmpeg liest die Tonspur direkt vom Server der Plattform und gibt sie
als rohe Abtastwerte aus - einkanalig und stark heruntergerechnet, denn fuer
ein Bild von wenigen hundert Bildpunkten Breite braucht es keine
Studioqualitaet. Aus den Werten wird je Bildspalte der lauteste Ausschlag
ermittelt.

Es entsteht keine Zwischendatei; die Daten laufen durch eine Weiterleitung.
"""

from __future__ import annotations

import array
import subprocess
from typing import Callable, Optional

from .. import paths
from .errors import CancelledError, FevError

# Zum Zeichnen voellig ausreichend und klein genug, um schnell zu bleiben.
SAMPLE_RATE = 8000
READ_CHUNK = 64 * 1024

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

CancelCheck = Callable[[], bool]


class WaveformError(FevError):
    """Die Tonspur liess sich nicht auswerten."""


def extract_peaks(
    audio_url: str,
    duration: float,
    buckets: int = 900,
    should_cancel: Optional[CancelCheck] = None,
) -> list[float]:
    """
    Liefert je Bildspalte einen Wert zwischen 0 und 1.

    'duration' dient nur der Aufteilung; ist sie unbekannt, wird am Ende
    anhand der tatsaechlich gelesenen Menge nachjustiert.
    """
    if not audio_url:
        raise WaveformError("Zu diesem Video gibt es keine abrufbare Tonspur.")
    if not paths.ffmpeg_available():
        raise WaveformError("ffmpeg fehlt. Bitte setup.ps1 ausfuehren.")

    buckets = max(50, int(buckets))
    total_samples = max(1, int(max(1.0, duration) * SAMPLE_RATE))
    per_bucket = max(1, total_samples // buckets)

    command = [
        str(paths.FFMPEG_EXE),
        "-v", "error",
        "-i", audio_url,
        "-vn",                      # Bildspur ignorieren
        "-ac", "1",                 # auf einen Kanal mischen
        "-ar", str(SAMPLE_RATE),
        "-f", "s16le",              # rohe Werte, 16 Bit
        "-",
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_NO_WINDOW,
    )

    peaks: list[float] = []
    current_peak = 0
    counted = 0
    leftover = b""

    try:
        while True:
            if should_cancel is not None and should_cancel():
                process.terminate()
                raise CancelledError("Abgebrochen.")

            chunk = process.stdout.read(READ_CHUNK)
            if not chunk:
                break

            data = leftover + chunk
            # Ein Abtastwert belegt zwei Bytes - ein einzelnes uebriges Byte
            # gehoert zum naechsten Block.
            usable = len(data) - (len(data) % 2)
            leftover = data[usable:]
            samples = array.array("h")
            samples.frombytes(data[:usable])

            for value in samples:
                magnitude = -value if value < 0 else value
                if magnitude > current_peak:
                    current_peak = magnitude
                counted += 1
                if counted >= per_bucket:
                    peaks.append(current_peak / 32768.0)
                    current_peak = 0
                    counted = 0
    finally:
        try:
            process.stdout.close()
        except Exception:
            pass
        stderr_output = b""
        try:
            stderr_output = process.stderr.read() or b""
            process.stderr.close()
        except Exception:
            pass
        process.wait(timeout=10)

    if counted:
        peaks.append(current_peak / 32768.0)

    if not peaks:
        detail = stderr_output.decode("utf-8", "replace").strip()
        raise WaveformError(
            "Die Tonspur liess sich nicht lesen." + (f"\n{detail}" if detail else "")
        )

    return _normalise(peaks)


def _normalise(peaks: list[float]) -> list[float]:
    """
    Hebt die Werte auf den lautesten Ausschlag an.

    Ohne das waere eine leise aufgenommene Spur nur ein flacher Strich.
    """
    loudest = max(peaks)
    if loudest <= 0.0001:
        return [0.0] * len(peaks)
    return [min(1.0, value / loudest) for value in peaks]
