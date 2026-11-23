"""Prüft Rubric-Struktur und meldet Qualitätsabweichungen ohne Änderungen."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from grading_pipeline.validation.numbers import parse_finite_number, same_number


class RubricValidationTarget(Protocol):
    """Zielpfad und Punktvorgabe einer Rubric."""

    path_string: str
    max_points: int | float | None


def validate_rubric_structure(
    data: dict[str, Any], target: RubricValidationTarget
) -> dict[str, Any]:
    """Fordert nur die zum Zuordnen und Speichern benötigte Grundstruktur."""
    if data.get("target_path") != target.path_string:
        raise ValueError(f"Rubric fuer {target.path_string}: target_path wurde veraendert.")
    criteria = data.get("criteria")
    if not isinstance(criteria, list):
        raise ValueError(f"Rubric fuer {target.path_string}: criteria ist kein JSON-Array.")
    if any(not isinstance(criterion, dict) for criterion in criteria):
        raise ValueError(f"Rubric fuer {target.path_string}: criteria enthaelt kein JSON-Objekt.")
    return data


def validate_rubric(
    data: dict[str, Any],
    target: RubricValidationTarget,
    *,
    warn: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Meldet Qualitätsprobleme einer Rubric, ohne Modellwerte zu ersetzen."""
    report = warn or (lambda _message: None)
    validate_rubric_structure(data, target)
    maximum = (
        None
        if target.max_points is None and data.get("max_points") is None
        else _number(data.get("max_points"), f"Rubric {target.path_string}.max_points", report)
    )
    if (target.max_points is None) != (maximum is None) or (
        maximum is not None
        and target.max_points is not None
        and not same_number(maximum, target.max_points)
    ):
        report(
            f"WARNUNG: Rubric {target.path_string}: max_points ist {data.get('max_points')!r}, "
            f"vorgegeben ist {target.max_points!r}."
        )
    criteria = data["criteria"]
    if not criteria:
        raise ValueError(f"Rubric fuer {target.path_string}: criteria ist leer.")
    points = [
        _criterion(criterion, f"Rubric {target.path_string}, Kriterium {index}", report)
        for index, criterion in enumerate(criteria, start=1)
    ]
    if target.max_points is not None and all(value is not None for value in points):
        total = sum(value for value in points if value is not None)
        if not same_number(total, target.max_points):
            report(
                f"WARNUNG: Rubric fuer {target.path_string}: Kriterien ergeben "
                f"{total:g} statt {target.max_points:g} Punkte."
            )
    return data


def _criterion(
    criterion: dict[str, Any], location: str, warn: Callable[[str], None]
) -> float | None:
    """Prüft ein Kriterium und seine bewertbaren Teilleistungen."""
    _require(criterion, {"id", "description", "points", "full_credit", "credit_items"}, location)
    _id(criterion["id"], f"{location}.id")
    _text(criterion["description"], f"{location}.description", warn)
    _text(criterion["full_credit"], f"{location}.full_credit", warn)
    alternatives = criterion.get("acceptable_alternatives")
    if alternatives is not None:
        _text(alternatives, f"{location}.acceptable_alternatives", warn)
    points = _number(criterion["points"], f"{location}.points", warn)
    items = criterion["credit_items"]
    if not isinstance(items, list) or not items:
        raise ValueError(f"{location}: credit_items muss ein nichtleeres JSON-Array sein.")
    item_points = [
        _credit_item(item, f"{location}.credit_items[{index}]", warn)
        for index, item in enumerate(items)
    ]
    if points is not None and all(value is not None for value in item_points):
        total = sum(value for value in item_points if value is not None)
        if not same_number(total, points):
            warn(f"WARNUNG: {location}: credit_items ergeben {total:g} statt {points:g} Punkte.")
    return points


def _credit_item(
    item: Any, location: str, warn: Callable[[str], None]
) -> float | None:
    """Prüft eine einzelne bewertbare Teilleistung."""
    if not isinstance(item, dict):
        raise ValueError(f"{location}: kein JSON-Objekt.")
    _require(item, {"id", "points", "requirement"}, location)
    _id(item["id"], f"{location}.id")
    _text(item["requirement"], f"{location}.requirement", warn)
    return _number(item["points"], f"{location}.points", warn)


def _require(data: dict[str, Any], fields: set[str], location: str) -> None:
    """Fordert die zur Qualitätsprüfung benötigten Felder."""
    if missing := fields - data.keys():
        raise ValueError(f"{location}: fehlende Felder {sorted(missing)}.")


def _text(value: Any, location: str, warn: Callable[[str], None]) -> None:
    """Fordert Text und meldet leeren Inhalt."""
    if not isinstance(value, str):
        raise ValueError(f"{location} muss ein JSON-String sein.")
    if not value.strip():
        warn(f"WARNUNG: {location} ist leer.")


def _id(value: Any, location: str) -> None:
    """Fordert nur den String-Typ einer frei benennbaren ID."""
    if not isinstance(value, str):
        raise ValueError(f"{location} muss ein JSON-String sein.")


def _number(value: Any, location: str, warn: Callable[[str], None]) -> float | None:
    """Liest positive Punkte für Vergleiche und lässt den Quellwert unverändert."""
    if isinstance(value, str):
        try:
            parsed = parse_finite_number(float(value.strip()), location=location)
        except (TypeError, ValueError):
            parsed = None
        if parsed is not None:
            warn(f"WARNUNG: {location} ist als Text {value!r} angegeben.")
            return parsed
    try:
        return parse_finite_number(value, location=location)
    except ValueError:
        warn(f"WARNUNG: {location} enthaelt den unbrauchbaren Wert {value!r}.")
        return None
