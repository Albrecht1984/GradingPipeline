"""Stellt Heartbeat-Meldungen und eine gemeinsame Laufzeitformatierung bereit."""

from __future__ import annotations

import threading
import time
from types import TracebackType
from typing import Callable


class ProgressHeartbeat:
    """Meldet waehrend eines blockierenden Modellaufrufs regelmaessig die Laufzeit."""

    def __init__(
        self,
        report: Callable[[str], None],
        label: str,
        interval: float = 30.0,
    ) -> None:
        """Konfiguriert Reporter, Meldungsbezeichnung und Heartbeat-Intervall."""

        if interval <= 0:
            raise ValueError("Das Heartbeat-Intervall muss groesser als 0 sein.")
        self.report = report
        self.label = label
        self.interval = interval
        self.started_at = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "ProgressHeartbeat":
        """Startet den Daemon-Thread und beginnt die Laufzeitmessung."""

        self.started_at = time.perf_counter()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="own-pix-progress-heartbeat",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Beendet den Heartbeat unabhaengig vom Ergebnis des Modellaufrufs."""

        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        """Wartet intervallweise und sendet formatierte Laufzeitmeldungen."""

        while not self._stop.wait(self.interval):
            elapsed = time.perf_counter() - self.started_at
            self.report(f"{self.label} laeuft seit {format_duration(elapsed)} ...")


def format_duration(seconds: float) -> str:
    """Formatiert eine Laufzeit gerundet als Minuten- oder Stundenangabe."""

    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d} h"
    return f"{minutes:02d}:{secs:02d} min"
