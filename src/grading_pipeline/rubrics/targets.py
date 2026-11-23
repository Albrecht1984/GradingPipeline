"""Ordnet Aufgabenstellung und Musterlösung zu Rubric-Zielen zu."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from grading_pipeline.infrastructure.task_nodes import (
    child_nodes,
    node_label,
    structural_path,
)
from grading_pipeline.validation.numbers import parse_optional_positive_points


@dataclass(frozen=True)
class RubricTarget:
    """Beschreibt ein strukturell ausgerichtetes Blattziel für eine Rubric."""

    path_string: str
    display_label: str
    assignment_node: dict[str, Any]
    reference_node: dict[str, Any]
    max_points: int | float | None


def build_rubric_targets(
    assignment: dict[str, Any],
    reference_solution: dict[str, Any],
) -> list[RubricTarget]:
    """Prueft beide Dokumentbaeume und erzeugt ein Ziel je Blattknoten."""

    assignment_tasks = assignment["tasks"]
    reference_tasks = reference_solution["tasks"]
    if len(assignment_tasks) != len(reference_tasks):
        raise ValueError(
            "Strukturabweichung bei tasks: "
            f"Aufgabenstellung={len(assignment_tasks)}, "
            f"Musterloesung={len(reference_tasks)}."
        )
    targets: list[RubricTarget] = []
    for index, (assignment_task, reference_task) in enumerate(
        zip(assignment_tasks, reference_tasks)
    ):
        _compare_nodes(
            assignment_task,
            reference_task,
            path=(index,),
            labels=(),
            targets=targets,
        )
    if not targets:
        raise ValueError("Die Dokumente enthalten keine bewertbaren Blattknoten.")
    return targets


def _compare_nodes(
    assignment_node: Any,
    reference_node: Any,
    *,
    path: tuple[int, ...],
    labels: tuple[str, ...],
    targets: list[RubricTarget],
) -> None:
    """Vergleicht zwei Knoten rekursiv und sammelt ausgerichtete Blaetter."""

    path_string = structural_path(path)
    if not isinstance(assignment_node, dict) or not isinstance(reference_node, dict):
        raise ValueError(f"Strukturabweichung bei {path_string}: Knoten fehlt.")
    assignment_label = node_label(assignment_node, path_string)
    assignment_children = child_nodes(
        assignment_node, f"Aufgabenstellung: {path_string}"
    )
    reference_children = child_nodes(
        reference_node, f"Musterloesung: {path_string}"
    )
    if len(assignment_children) != len(reference_children):
        raise ValueError(
            f"Strukturabweichung bei {path_string}: "
            f"Aufgabenstellung={len(assignment_children)} Unterknoten, "
            f"Musterloesung={len(reference_children)} Unterknoten."
        )
    if assignment_children:
        for index, (assignment_child, reference_child) in enumerate(
            zip(assignment_children, reference_children)
        ):
            _compare_nodes(
                assignment_child,
                reference_child,
                path=(*path, index),
                labels=(*labels, assignment_label),
                targets=targets,
            )
        return

    try:
        points = parse_optional_positive_points(
            assignment_node.get("points"),
            location=f"{path_string}.points",
        )
    except ValueError:
        points = None
    targets.append(
        RubricTarget(
            path_string=path_string,
            display_label=" / ".join((*labels, assignment_label)),
            assignment_node=assignment_node,
            reference_node=reference_node,
            max_points=points,
        )
    )
def _source_metadata(target: RubricTarget) -> dict[str, Any]:
    """Liefert die gemeinsamen Quellenbezeichnungen eines Rubric-Ziels."""

    return {
        "assignment_id": target.assignment_node.get("id"),
        "assignment_source_label": target.assignment_node.get("source_label"),
        "reference_solution_id": target.reference_node.get("id"),
        "reference_solution_source_label": target.reference_node.get("source_label"),
    }


def target_input_payload(target: RubricTarget) -> str:
    """Serialisiert die Metadaten eines Rubric-Ziels fuer den Modellprompt."""

    return json.dumps(
        {
            "target_path": target.path_string,
            **_source_metadata(target),
            "max_points": target.max_points,
        },
        ensure_ascii=False,
        indent=2,
    )


def combine_target_and_rubric(
    target: RubricTarget,
    rubric: dict[str, Any],
) -> dict[str, Any]:
    """Verbindet Zielmetadaten mit der validierten Modellrubric."""

    return {
        "target_path": target.path_string,
        "display_label": target.display_label,
        **_source_metadata(target),
        "title": target.assignment_node.get("title"),
        "max_points": rubric.get("max_points"),
        "criteria": rubric["criteria"],
    }
