"""Hintergrund-Threads.

Analysieren und Herunterladen dauern Sekunden bis Minuten. Beides laeuft daher
in eigenen Threads - sonst wuerde das Fenster einfrieren und Windows es als
"reagiert nicht" melden.
"""

from __future__ import annotations

import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, Optional, Sequence

from PySide6.QtCore import QMutex, QMutexLocker, QObject, QThread, QWaitCondition, Signal

from ..core import appupdate
from ..core.download import download, download_preview
from ..core.errors import CancelledError, FevError
from ..core.models import DownloadRequest, Progress
from ..core.probe import probe
from ..core.thumbs import ensure_thumbnail
from ..core.update import auto_update_ytdlp
from ..core.waveform import extract_peaks

# Wie viele Ausschnitte gleichzeitig geladen werden. Gemessen: bei drei blieb
# der Durchsatz je Verbindung nahezu gleich, darueber sank er merklich.
MAX_PARALLEL = 3


class ProbeWorker(QThread):
    """Fragt die Metadaten eines Links ab."""

    succeeded = Signal(object)   # VideoInfo
    failed = Signal(str)

    def __init__(self, url: str, parent=None) -> None:
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        try:
            self.succeeded.emit(probe(self._url))
        except FevError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Unerwarteter Fehler: {exc}")


class ThumbnailWorker(QThread):
    """Laedt das Vorschaubild herunter."""

    loaded = Signal(bytes)

    def __init__(self, url: str, parent=None) -> None:
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        try:
            request = urllib.request.Request(
                self._url,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                self.loaded.emit(response.read())
        except Exception:
            # Ein fehlendes Vorschaubild ist kein Grund, den Nutzer zu stoeren.
            pass


class PreviewWorker(QThread):
    """Holt eine kleine Vorschaudatei, wenn der Stream nicht abspielbar ist."""

    succeeded = Signal(object)  # Path
    failed = Signal(str)

    def __init__(self, url: str, target_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self._url = url
        self._target_dir = target_dir
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        try:
            result = download_preview(
                self._url,
                self._target_dir,
                should_cancel=lambda: self._cancel_requested,
            )
            self.succeeded.emit(result)
        except CancelledError:
            pass
        except FevError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Unerwarteter Fehler: {exc}")


class WaveformWorker(QThread):
    """Berechnet die Wellenform der Tonspur."""

    succeeded = Signal(object)  # list[float]
    failed = Signal(str)

    def __init__(self, audio_url: str, duration: float, buckets: int = 900, parent=None) -> None:
        super().__init__(parent)
        self._audio_url = audio_url
        self._duration = duration
        self._buckets = buckets
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        try:
            peaks = extract_peaks(
                self._audio_url,
                self._duration,
                buckets=self._buckets,
                should_cancel=lambda: self._cancel_requested,
            )
            self.succeeded.emit(peaks)
        except CancelledError:
            pass
        except FevError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Unerwarteter Fehler: {exc}")


class LibraryThumbWorker(QThread):
    """
    Erzeugt die Vorschaubilder der Bibliothek, eines nach dem anderen.

    Bewusst ein einziger, dauerhaft laufender Thread mit Warteschlange: Bei
    jedem Filterwechsel einen neuen zu starten und den alten abzuraeumen waere
    ein staendiges Kommen und Gehen von Threads - und jedes Mal die Frage, ob
    der alte schon fertig ist. So wird stattdessen nur die Liste ausgetauscht.
    """

    ready = Signal(str, str)  # Quelldatei, Vorschaubild

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mutex = QMutex()
        self._pending = QWaitCondition()
        self._queue: list[tuple[str, str]] = []
        self._stop = False

    def submit(self, jobs: Iterable[tuple[str, str]]) -> None:
        """Ersetzt die Warteschlange - was nicht mehr sichtbar ist, entfaellt."""
        with QMutexLocker(self._mutex):
            if self._stop:
                return
            self._queue = list(jobs)
            self._pending.wakeAll()
        if not self.isRunning():
            self.start()

    def stop(self) -> None:
        with QMutexLocker(self._mutex):
            self._stop = True
            self._queue = []
            self._pending.wakeAll()

    def run(self) -> None:
        while True:
            self._mutex.lock()
            while not self._queue and not self._stop:
                self._pending.wait(self._mutex)
            if self._stop:
                self._mutex.unlock()
                return
            source, kind = self._queue.pop(0)
            self._mutex.unlock()

            try:
                thumbnail = ensure_thumbnail(Path(source), kind)
            except Exception:
                # Ein fehlendes Vorschaubild ist kein Grund, den Nutzer zu stoeren.
                thumbnail = None
            if thumbnail is not None:
                self.ready.emit(source, str(thumbnail))


class DownloadWorker(QThread):
    """
    Fuehrt einen oder mehrere Downloads aus und meldet den Fortschritt.

    Mehrere Auftraege entstehen, wenn sich der Nutzer mehrere Stellen desselben
    Videos gemerkt hat. Jeder durchlaeuft dieselbe Strecke wie ein einzelner
    Download - samt Wiederholversuchen, Namensgebung und H.264-Umwandlung.

    **Sie laufen gleichzeitig, und das ist der Grund fuer diese Klasse.**
    Gemessen an einem 15-Sekunden-Ausschnitt in 1080p kommen die Daten mit rund
    0,5 MB/s herein - unabhaengig davon, ob ein oder drei Downloads laufen. Die
    Bremse sitzt also in der einzelnen Verbindung, nicht in der Leitung. Drei
    Ausschnitte nacheinander brauchten in der Messung 42 s, gleichzeitig 17 s.

    Mehr als MAX_PARALLEL bringt nichts mehr: Ab drei sank der Durchsatz je
    Verbindung sichtbar, und drei ffmpeg-Vorgaenge auf einmal reichen aus.
    """

    progressed = Signal(object)  # Progress
    fileReady = Signal(object)   # Path - nach jedem fertigen Ausschnitt
    succeeded = Signal(object)   # Path - der letzte, wenn alles durch ist
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        requests: DownloadRequest | Sequence[DownloadRequest],
        parent=None,
    ) -> None:
        super().__init__(parent)
        if isinstance(requests, DownloadRequest):
            requests = [requests]
        self._requests: list[DownloadRequest] = list(requests)
        self._cancel_requested = False
        self._lock = threading.Lock()
        self._percent: list[float] = []
        self._speed: list[float] = []
        self._eta: list[int] = []
        self._done = 0

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        total = len(self._requests)
        self._percent = [0.0] * total
        self._speed = [0.0] * total
        self._eta = [0] * total
        self._done = 0

        results: list[Optional[Path]] = [None] * total
        errors: list[str] = []
        cancelled = False

        with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL, total)) as pool:
            auftraege = {
                pool.submit(self._download_one, index, request): index
                for index, request in enumerate(self._requests)
            }
            for future in as_completed(auftraege):
                index = auftraege[future]
                try:
                    results[index] = future.result()
                except CancelledError:
                    cancelled = True
                except FevError as exc:
                    errors.append(str(exc))
                except Exception as exc:
                    errors.append(f"Unerwarteter Fehler: {exc}")

        if cancelled:
            self.cancelled.emit()
            return
        if errors:
            # Was fertig wurde, ist ueber fileReady bereits gemeldet und bleibt
            # erhalten - nur die Fehlermeldung kommt noch obendrauf.
            self.failed.emit(errors[0])
            return

        fertig = [path for path in results if path is not None]
        if fertig:
            self.succeeded.emit(fertig[-1])

    def _download_one(self, index: int, request: DownloadRequest) -> Path:
        result: Path = download(
            request,
            on_progress=self._make_reporter(index, len(self._requests)),
            should_cancel=lambda: self._cancel_requested,
        )
        with self._lock:
            self._done += 1
            self._percent[index] = 100.0
            self._speed[index] = 0.0
            self._eta[index] = 0
        # Sofort melden, nicht erst am Ende: So wandert jeder Ausschnitt in den
        # Media Pool, sobald er da ist.
        self.fileReady.emit(result)
        return result

    def _make_reporter(self, index: int, total: int):
        """
        Baut die Fortschrittsmeldung fuer einen der Auftraege.

        Bei einem einzelnen Auftrag wird sie unveraendert durchgereicht. Bei
        mehreren muessen die gleichzeitigen Meldungen zusammengefasst werden -
        sonst spraenge der Balken zwischen drei Downloads hin und her.
        """
        if total == 1:
            return self.progressed.emit

        def report(progress: Progress) -> None:
            with self._lock:
                if progress.status == "downloading":
                    self._percent[index] = progress.percent
                    self._speed[index] = progress.speed or 0.0
                    self._eta[index] = progress.eta or 0
                elif progress.status == "processing":
                    # Geladen ist geladen - das Verarbeiten zaehlt als fertig,
                    # sonst haengt der Balken bei 99 Prozent fest.
                    self._percent[index] = 100.0
                    self._speed[index] = 0.0
                    self._eta[index] = 0

                gesamt = sum(self._percent) / total
                tempo = sum(self._speed)
                rest = max(self._eta)
                fertig = self._done

            self.progressed.emit(
                Progress(
                    status="downloading",
                    percent=gesamt,
                    # Zusammengezaehlt ueber alle laufenden Downloads.
                    speed=tempo or None,
                    eta=rest or None,
                    part=fertig,
                    parts=total,
                )
            )

        return report


class UpdateNotifier(QObject):
    """
    Meldet dem Fenster, was die Pruefung beim Start gefunden hat.

    Die Pruefung selbst laeuft in einem gewoehnlichen Thread (siehe
    start_startup_check), nicht in einem QThread: Haengt das Netz, soll das
    Schliessen des Fensters nicht darauf warten muessen. Ein QThread muesste
    beim Beenden abgewartet werden, ein 'daemon'-Thread wird einfach beendet.
    """

    ytdlpUpdated = Signal(str)       # neue yt-dlp-Fassung, gilt ab dem naechsten Start
    appUpdateFound = Signal(object)  # AppRelease


def run_startup_checks(notifier: UpdateNotifier, check_app: bool = True, check_ytdlp: bool = True) -> None:
    """Beide Suchen nacheinander. Fehler bleiben still - das ist nur ein Angebot."""
    try:
        if check_ytdlp:
            result = auto_update_ytdlp()
            if result is not None and result.changed:
                notifier.ytdlpUpdated.emit(result.version)
        if check_app:
            release = appupdate.check()
            if release is not None:
                notifier.appUpdateFound.emit(release)
    except RuntimeError:
        # Das Fenster wurde waehrenddessen geschlossen und der Melder mit ihm.
        pass
    except Exception:
        pass


def start_startup_check(notifier: UpdateNotifier, **kwargs) -> threading.Thread:
    thread = threading.Thread(
        target=run_startup_checks,
        args=(notifier,),
        kwargs=kwargs,
        name="fevdl-update-check",
        daemon=True,
    )
    thread.start()
    return thread


class AppUpdateWorker(QThread):
    """Laedt den Installer einer neuen Fassung herunter und prueft ihn."""

    progress = Signal(int)       # 0..100
    succeeded = Signal(object)   # Path des Installers
    failed = Signal(str)

    def __init__(self, release: "appupdate.AppRelease", parent=None) -> None:
        super().__init__(parent)
        self._release = release
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        try:
            path = appupdate.download_installer(
                self._release,
                on_progress=self.progress.emit,
                should_cancel=lambda: self._cancel_requested,
            )
            self.succeeded.emit(path)
        except appupdate.UpdateError as exc:
            if not self._cancel_requested:
                self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Unerwarteter Fehler: {exc}")
