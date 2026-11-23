"""Zentrale Regeln für Punktwerte und tolerante Zahlenvergleiche."""

from __future__ import annotations

import math
from typing import Any


NUMBER_TOLERANCE = 1e-9
GRADING_NUMBER_TOLERANCE = 1e-6


def is_finite_number(value: Any) -> bool:
    """Prüft einen Wert auf eine endliche Zahl und schließt Booleans aus."""
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def parse_finite_number(
    value: Any,
    *,
    location: str,
    allow_zero: bool = False,
) -> float:
    """Parst eine endliche positive oder optional nicht negative Zahl."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{location} muss eine Zahl sein.")
    result = float(value)
    valid = result >= 0 if allow_zero else result > 0
    if not math.isfinite(result) or not valid:
        comparator = "nicht negativ" if allow_zero else "positiv"
        raise ValueError(f"{location} muss endlich und {comparator} sein.")
    return result


def parse_optional_positive_points(
    value: Any,
    *,
    location: str,
) -> float | None:
    """Parst eine positive endliche Punktzahl oder ein bewusstes JSON-null."""
    if value is None:
        return None
    try:
        return parse_finite_number(value, location=location)
    except ValueError as exc:
        raise ValueError(
            f"{location} muss eine positive endliche Zahl oder null sein."
        ) from exc


def same_number(
    value: Any,
    expected: int | float,
    *,
    tolerance: float = NUMBER_TOLERANCE,
) -> bool:
    """Vergleicht eine ungeprüfte Zahl absolut mit einer expliziten Toleranz."""
    return is_finite_number(value) and math.isclose(
        float(value),
        float(expected),
        rel_tol=0.0,
        abs_tol=tolerance,
    )
