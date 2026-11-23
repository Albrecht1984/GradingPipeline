"""Nachvollziehbarer Bericht ueber die gepruefte Bewertungsstruktur."""

from __future__ import annotations

from typing import Any

from grading_pipeline.infrastructure.hashing import sha256_file

from .context import LoadedTaskContextMap
from .documents import LoadedDocument, source_payload
from .structure import GradingUnit


def structure_check_payload(
    *,
    assignment: LoadedDocument,
    student_solution: LoadedDocument,
    reference_solution: LoadedDocument | None,
    rubrics: LoadedDocument | None,
    units: list[GradingUnit],
    task_context_map: LoadedTaskContextMap | None = None,
) -> dict[str, Any]:
    """Erzeugt das nachvollziehbare Ergebnis der Strukturpruefung."""

    return {
        "status": "valid",
        "assignment": source_payload(assignment),
        "student_solution": source_payload(student_solution),
        "reference_solution": (
            source_payload(reference_solution) if reference_solution else None
        ),
        "rubrics": source_payload(rubrics) if rubrics else None,
        "task_context_map": (
            {"path": task_context_map.path.name} if task_context_map else None
        ),
        "grading_unit_count": len(units),
        "units": [
            {
                "target_path": unit.path_string,
                "display_label": unit.display_label,
                "max_points": unit.max_points,
                "reference_solution_available": (
                    unit.reference_solution_node is not None
                ),
                "rubric_available": unit.rubric is not None,
                "context_material": [
                    {
                        "path": item.path.name,
                        "sha256": sha256_file(item.path),
                    }
                    for item in (
                        task_context_map.by_target_path.get(unit.path_string, [])
                        if task_context_map
                        else []
                    )
                ],
            }
            for unit in units
        ],
    }
