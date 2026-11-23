"""Gemeinsamer Ergebnistyp für vollständig und unvollständig verarbeitete Läufe."""

from typing import Literal


ResultStatus = Literal["complete", "incomplete"]


def result_status(*, has_failures: bool) -> ResultStatus:
    """Leitet den typisierten Gesamtstatus aus vorhandenen Fehlern ab."""

    return "incomplete" if has_failures else "complete"
