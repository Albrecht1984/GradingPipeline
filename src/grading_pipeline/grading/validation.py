"""Prüft verarbeitbare Bewertungsantworten und meldet inhaltliche Abweichungen."""
from __future__ import annotations
from typing import Any, Callable
from .schema import AssessmentItem, TaskGrading
from grading_pipeline.validation.numbers import (
    GRADING_NUMBER_TOLERANCE,
    parse_finite_number,
    same_number,
)

EXPECTED_RESPONSE_FIELDS = {
    "points",
    "max_points",
    "assessment_items",
    "summary",
    "student_feedback",
}
EXPECTED_ITEM_FIELDS = {
    "id",
    "description",
    "points",
    "max_points",
    "comment",
}


def validate_grading_response(
    data: dict[str, Any], *, target_path: str, display_label: str,
    expected_max_points: int | float | None,
    warn: Callable[[str], None] | None = None,
) -> TaskGrading:
    """Erhält Modellinhalte; unbrauchbare Punktwerte werden als unbekannt übernommen."""
    return _read_grading_response(
        data, target_path=target_path, display_label=display_label,
        expected_max_points=expected_max_points, warn=warn,
    )


def parse_grading_response(
    data: dict[str, Any], *, target_path: str, display_label: str,
    expected_max_points: int | float | None,
) -> TaskGrading:
    """Liest nur die technisch benötigte Bewertungsstruktur ohne Qualitätshinweise."""
    return _read_grading_response(
        data, target_path=target_path, display_label=display_label,
        expected_max_points=expected_max_points, warn=None,
    )


def _read_grading_response(
    data: dict[str, Any], *, target_path: str, display_label: str,
    expected_max_points: int | float | None,
    warn: Callable[[str], None] | None,
) -> TaskGrading:
    """Parst eine Bewertung und schaltet Qualitätsmeldungen optional hinzu."""
    _require_fields(data, EXPECTED_RESPONSE_FIELDS, target_path)
    summary = required_text(data["summary"], "summary", warn=warn)
    feedback = required_text(data["student_feedback"], "student_feedback", warn=warn)
    raw_items = data["assessment_items"]
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("assessment_items muss eine nicht leere Liste sein.")
    unscored = expected_max_points is None
    points = _points(
        data["points"], "points", unscored=unscored, allow_zero=True, warn=warn
    )
    maximum = _points(
        data["max_points"], "max_points", unscored=unscored, warn=warn
    )
    if warn is not None and unscored:
        if points is not None or maximum is not None:
            warn(f"WARNUNG: {target_path}: ohne Punktvorgabe werden points/max_points=null erwartet; "
                 f"erhalten {points!r}/{maximum!r}.")
    elif warn is not None:
        if maximum is not None and not same_number(
            maximum,
            expected_max_points,
            tolerance=GRADING_NUMBER_TOLERANCE,
        ):
            warn(
                f"WARNUNG: {target_path}: max_points ist {maximum:g}, "
                f"erwartet wurden {expected_max_points:g}."
            )
    if (warn is not None and points is not None and maximum is not None
            and points > maximum + GRADING_NUMBER_TOLERANCE):
        warn(f"WARNUNG: {target_path}: points {points:g} ueberschreitet max_points {maximum:g}.")
    items = tuple(validate_item(item, unscored=unscored, warn=warn) for item in raw_items)
    if warn is not None and not unscored:
        for field, actual in (("points", points), ("max_points", maximum)):
            values = [getattr(item, field) for item in items]
            if actual is None or any(value is None for value in values):
                continue
            total = sum(values)
            if not same_number(total, actual, tolerance=GRADING_NUMBER_TOLERANCE):
                warn(f"WARNUNG: {target_path}: assessment_items.{field} ergeben {total:g} statt {actual:g}.")
    return TaskGrading(target_path=target_path, display_label=display_label,
                       points=points, max_points=maximum, assessment_items=items,
                       summary=summary, student_feedback=feedback)


def _require_fields(data: dict[str, Any], expected: set[str], location: str) -> None:
    """Fordert die Felder, die zum Erzeugen eines Bewertungsergebnisses nötig sind."""
    missing = expected - set(data)
    if missing:
        raise ValueError(f"{location}: fehlende Felder {sorted(missing)}.")


def _points(
    value: Any,
    location: str,
    *,
    unscored: bool,
    warn: Callable[[str], None] | None,
    allow_zero: bool = False,
) -> float | None:
    """Liest Punkte und meldet unbrauchbare Werte als unbekannt."""
    if unscored and value is None:
        return None
    try:
        return parse_finite_number(value, location=location, allow_zero=allow_zero)
    except ValueError as exc:
        if warn is not None:
            warn(f"WARNUNG: {exc} Der Wert wird als unbekannt behandelt.")
        return None


def validate_item(data: Any, *, unscored: bool,
                  warn: Callable[[str], None] | None = None) -> AssessmentItem:
    """Prüft einen Bewertungsaspekt und meldet Punktabweichungen ohne Korrektur."""
    if not isinstance(data, dict):
        raise ValueError("assessment_item muss ein JSON-Objekt sein.")
    _require_fields(data, EXPECTED_ITEM_FIELDS, "assessment_item")
    item_id = required_text(data["id"], "assessment_item.id", warn=warn)
    description = required_text(data["description"], "assessment_item.description", warn=warn)
    comment = required_text(data["comment"], "assessment_item.comment", warn=warn)
    points = _points(
        data["points"],
        f"assessment_item {item_id}.points",
        unscored=unscored,
        allow_zero=True,
        warn=warn,
    )
    maximum = _points(
        data["max_points"],
        f"assessment_item {item_id}.max_points",
        unscored=unscored,
        warn=warn,
    )
    if warn is not None and unscored and (points is not None or maximum is not None):
        warn(f"WARNUNG: assessment_item {item_id}: ohne Punktvorgabe werden null-Werte erwartet, "
             f"erhalten {points!r}/{maximum!r}.")
    if (warn is not None and points is not None and maximum is not None
            and points > maximum + GRADING_NUMBER_TOLERANCE):
        warn(f"WARNUNG: assessment_item {item_id}: points {points:g} ueberschreitet max_points {maximum:g}.")
    return AssessmentItem(id=item_id, description=description, points=points, max_points=maximum, comment=comment)


def required_text(value: Any, location: str, *, warn: Callable[[str], None] | None = None) -> str:
    """Fordert einen String; leere Texte werden nur gemeldet und unverändert erhalten."""
    if not isinstance(value, str):
        raise ValueError(f"{location} muss ein Text sein.")
    if not value.strip() and warn is not None:
        warn(f"WARNUNG: {location} ist leer.")
    return value
