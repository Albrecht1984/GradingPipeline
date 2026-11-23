"""Formatierung einzelner Bewertungseinheiten für den Grader."""

from __future__ import annotations

import html
import json
from typing import Any

from grading_pipeline.infrastructure.pipeline_artifacts import ContextMaterial
from grading_pipeline.infrastructure.task_nodes import joined_node_text
from .structure import GradingUnit


def build_grader_input(
    unit: GradingUnit,
    *,
    context_material: list[ContextMaterial],
) -> str:
    """Setzt die getrennt erzeugten Abschnitte zu einem Modellinput zusammen."""

    parts = ["<BEWERTUNGSEINHEIT>", *grading_content_sections(unit)]
    if unit.rubric is not None:
        parts.append(rubric_section(unit.rubric))
    if context_material:
        parts.append(context_material_section(context_material))
    parts.append("</BEWERTUNGSEINHEIT>")
    return "\n\n".join(parts)


def grading_content_sections(unit: GradingUnit) -> list[str]:
    """Erzeugt Aufgaben-, Loesungs- und optionale Musterloesungsabschnitte."""

    max_points = "null" if unit.max_points is None else f"{unit.max_points:g}"
    parts: list[str] = []
    if unit.assignment_context.strip():
        parts.append(tagged_section("AUFGABENKONTEXT", unit.assignment_context))
    parts.append(
        tagged_section(
            f'AUFGABE max_points="{max_points}"',
            node_markdown(unit.assignment_node) or "[KEIN AUFGABENTEXT]",
            closing_tag="AUFGABE",
        )
    )
    if unit.student_solution_context.strip():
        parts.append(
            tagged_section("LOESUNGSKONTEXT", unit.student_solution_context)
        )
    parts.append(
        tagged_section(
            "STUDENTISCHE_LOESUNG",
            node_markdown(unit.student_solution_node) or "[KEINE ANTWORT]",
        )
    )
    if unit.reference_solution_node is not None:
        if unit.reference_solution_context.strip():
            parts.append(
                tagged_section(
                    "MUSTERLOESUNGSKONTEXT", unit.reference_solution_context
                )
            )
        parts.append(
            tagged_section(
                "MUSTERLOESUNG",
                node_markdown(unit.reference_solution_node)
                or "[KEINE MUSTERLOESUNG]",
            )
        )
    return parts


def rubric_section(rubric: dict[str, Any]) -> str:
    """Serialisiert die fuer das Modell relevanten Felder einer Rubric."""

    grader_rubric = {
        key: value
        for key, value in rubric.items()
        if key not in {"target_path", "max_points"}
    }
    return (
        "<RUBRIC>\n"
        + json.dumps(grader_rubric, ensure_ascii=False, indent=2)
        + "\n</RUBRIC>"
    )


def context_material_section(context_material: list[ContextMaterial]) -> str:
    """Formatiert zusaetzliche Dateien als gemeinsamen Kontextabschnitt."""

    context_parts = []
    for item in context_material:
        name = html.escape(item.path.name, quote=True)
        context_parts.append(
            f'<DATEI name="{name}">\n{item.content.strip()}\n</DATEI>'
        )
    return "<KONTEXTMATERIAL>\n" + "\n\n".join(context_parts) + "\n</KONTEXTMATERIAL>"


def node_markdown(node: dict[str, Any]) -> str:
    """Gibt ausschliesslich die sichtbaren Markdown-Felder eines Knotens zurueck."""
    return joined_node_text(
        node,
        ("introduction_markdown", "markdown", "closing_markdown"),
    )


def tagged_section(tag: str, content: str, *, closing_tag: str | None = None) -> str:
    """Umschliesst einen Inhalt mit einem XML-aehnlichen Tag-Paar."""

    closing = closing_tag or tag
    return f"<{tag}>\n{content.strip()}\n</{closing}>"
