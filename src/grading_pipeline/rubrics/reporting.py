"""Erzeugt Struktur- und Markdownberichte für Rubrics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .targets import RubricTarget


def structure_check_payload(
    *,
    assignment_path: Path,
    reference_path: Path,
    targets: list[RubricTarget],
) -> dict[str, Any]:
    """Erzeugt das nachvollziehbare Ergebnis der Strukturpruefung."""

    return {
        "status": "valid",
        "assignment_path": str(assignment_path),
        "reference_solution_path": str(reference_path),
        "rubric_target_count": len(targets),
        "targets": [
            {
                "target_path": target.path_string,
                "display_label": target.display_label,
                "max_points": target.max_points,
            }
            for target in targets
        ],
    }


def render_rubrics_markdown(data: dict[str, Any]) -> str:
    """Rendert die zusammengefuehrten Rubrics als lesbares Markdown."""

    parts = ["# Bewertungsrubrics"]
    for rubric in data["rubrics"]:
        heading = f"## {rubric['display_label']}"
        if rubric.get("max_points") is not None:
            heading += f" — {_format_points(rubric['max_points'])}"
        parts.append(heading)
        for index, criterion in enumerate(rubric["criteria"], start=1):
            parts.append(
                f"### {criterion.get('id') or f'Kriterium {index}'}"
                f" — {_format_points(criterion.get('points'))}"
            )
            parts.append(_text(criterion.get("description")))
            parts.append(f"**Volle Punktzahl:** {_text(criterion.get('full_credit'))}")
            credit_items = criterion.get("credit_items")
            if not isinstance(credit_items, list):
                credit_items = []
            items = "\n".join(
                f"- **{item.get('id') or 'Teilleistung'} — {_format_points(item.get('points'))}:** "
                f"{_text(item.get('requirement'))}"
                for item in credit_items
                if isinstance(item, dict)
            )
            parts.append(f"**Bewertbare Teilleistungen:**\n\n{items}")
            alternatives = criterion.get("acceptable_alternatives")
            if alternatives:
                parts.append(f"**Zulässige Alternativen:** {_text(alternatives)}")
    return "\n\n".join(parts).strip()


def _format_points(points: Any) -> str:
    """Formatiert eine Punktzahl mit passendem Singular oder Plural."""

    if isinstance(points, bool) or not isinstance(points, (int, float)):
        return "Punktzahl offen"
    value = str(points) if isinstance(points, int) else f"{points:g}"
    return f"{value} Punkt" if points == 1 else f"{value} Punkte"


def _text(value: Any) -> str:
    """Liest Modelltext tolerant für den manuellen Rubric-Bericht."""
    return value.strip() if isinstance(value, str) else ""
