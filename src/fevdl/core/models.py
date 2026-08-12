"""Datentypen, die zwischen Kernlogik und Oberflaeche wandern."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class Mode(str, Enum):
    """Was heruntergeladen werden soll."""

    VIDEO_AUDIO = "video_audio"
    AUDIO_ONLY = "audio_only"
    VIDEO_ONLY = "video_only"

    @property
    def label(self) -> str:
        return {
            Mode.VIDEO_AUDIO: "Video + Ton",
            Mode.AUDIO_ONLY: "Nur Ton",
            Mode.VIDEO_ONLY: "Nur Video (ohne Ton)",
        }[self]

    @property
    def needs_video(self) -> bool:
        return self is not Mode.AUDIO_ONLY

    @property
    def needs_audio(self) -> bool:
        return self is not Mode.VIDEO_ONLY


@dataclass(frozen=True, order=True)
class Quality:
    """Eine waehlbare Aufloesung, die es beim Video wirklich gibt."""

    height: int
    fps: Optional[int] = None

    @property
    def label(self) -> str:
        name = _HEIGHT_NAMES.get(self.height, f"{self.height}p")
        # Die Bildrate nur nennen, wenn sie ueber dem Ueblichen liegt.
        if self.fps and self.fps >= 50:
            return f"{name} · {self.fps}"
        return name


# Kurz halten - der Name steht in einem schmalen Auswahlfeld.
_HEIGHT_NAMES = {
    4320: "8K",
    2160: "4K",
    1440: "1440p",
    1080: "1080p",
    720: "720p",
    480: "480p",
    360: "360p",
    240: "240p",
    144: "144p",
}


@dataclass
class VideoInfo:
    """Was wir ueber ein Video wissen, bevor etwas geladen wird."""

    url: str
    title: str
    duration: float = 0.0
    uploader: str = ""
    thumbnail_url: str = ""
    preview_url: str = ""
    # Reine Tonspur - Grundlage fuer die Wellenform.
    audio_url: str = ""
    qualities: list[Quality] = field(default_factory=list)
    extractor: str = ""
    is_live: bool = False
    # Bildformat der Quelle - entscheidet, wie die Vorschau dargestellt wird.
    width: int = 0
    height: int = 0

    @property
    def duration_text(self) -> str:
        return format_timecode(self.duration)

    @property
    def aspect(self) -> float:
        """Seitenverhaeltnis (Breite geteilt durch Hoehe). 16:9 ergibt 1.78."""
        if self.width > 0 and self.height > 0:
            return self.width / self.height
        return 16 / 9

    @property
    def is_portrait(self) -> bool:
        """True bei Hochformat, wie es TikTok, Reels und Shorts liefern."""
        return self.aspect < 0.95

    @property
    def best_height(self) -> Optional[int]:
        return self.qualities[0].height if self.qualities else None

    @property
    def has_video(self) -> bool:
        return bool(self.qualities)


@dataclass
class DownloadRequest:
    """Ein konkreter Auftrag an den Download-Motor."""

    url: str
    output_dir: Path
    mode: Mode = Mode.VIDEO_AUDIO
    height: Optional[int] = None
    start: Optional[float] = None
    end: Optional[float] = None
    # H.264/mp4 erzwingen. Resolve (besonders die kostenlose Version) kann mit
    # VP9- und AV1-Material nichts anfangen, das YouTube ab 1440p ausliefert.
    prefer_h264: bool = True

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        if self.start is not None and self.start <= 0:
            self.start = None
        if self.end is not None and self.end <= 0:
            self.end = None
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("Das Ende des Ausschnitts muss nach dem Anfang liegen.")

    @property
    def is_trimmed(self) -> bool:
        return self.start is not None or self.end is not None


@dataclass
class Progress:
    """Fortschrittsmeldung waehrend des Downloads."""

    status: str = "downloading"
    percent: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed: Optional[float] = None
    eta: Optional[int] = None
    message: str = ""
    # Bei mehreren gemerkten Ausschnitten: wie viele von wie vielen schon
    # fertig sind. Der Download-Motor selbst kennt immer nur einen Auftrag -
    # gefuellt wird das erst vom Thread, der die Auftraege verteilt. Weil sie
    # gleichzeitig laufen, zaehlt hier das Fertige und nicht "der wievielte".
    part: int = 0
    parts: int = 0

    @property
    def part_text(self) -> str:
        """'1/3 Ausschnitte fertig' - leer, solange es nur einen Auftrag gibt."""
        if self.parts > 1:
            return f"{self.part}/{self.parts} Ausschnitte fertig"
        return ""

    @property
    def speed_text(self) -> str:
        if not self.speed:
            return ""
        mb_per_second = self.speed / (1024 * 1024)
        return f"{mb_per_second:.1f} MB/s"

    @property
    def eta_text(self) -> str:
        if self.eta is None:
            return ""
        minutes, seconds = divmod(int(self.eta), 60)
        return f"noch {minutes}:{seconds:02d}"


def format_timecode(seconds: float) -> str:
    """Sekunden als H:MM:SS bzw. MM:SS darstellen."""
    if seconds is None or seconds < 0:
        seconds = 0
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_timecode(text: str) -> float:
    """'1:23', '01:02:03' oder '83' in Sekunden umrechnen."""
    text = (text or "").strip()
    if not text:
        return 0.0
    parts = text.split(":")
    if len(parts) > 3:
        raise ValueError(f"Ungueltige Zeitangabe: {text}")
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        raise ValueError(f"Ungueltige Zeitangabe: {text}") from None
    seconds = 0.0
    for number in numbers:
        seconds = seconds * 60 + number
    return seconds
