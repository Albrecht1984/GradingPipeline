"""Strukturelles Ausrichten der Dokumentbaeume zu Bewertungseinheiten."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from grading_pipeline.validation.numbers import parse_optional_positive_points
from grading_pipeline.infrastructure.task_nodes import (
    child_nodes,
    joined_node_text,
    node_label,
    structural_path,
)


@dataclass(frozen=True)
class GradingUnit:
    """Buendelt alle Inhalte einer einzelnen zu bewertenden Blattaufgabe."""

    path: tuple[int, ...]
    path_string: str
    display_label: str
    max_points: float | None
    assignment_node: dict[str, Any]
    assignment_context: str
    student_solution_node: dict[str, Any]
    student_solution_context: str
    reference_solution_node: dict[str, Any] | None
    reference_solution_context: str
    rubric: dict[str, Any] | None

@dataclass(frozen=True)
class ParallelNodeLists:
    """Haelt die parallel zu vergleichenden Knotenlisten der Dokumente."""

    assignment: Any
    student_solution: Any
    reference_solution: Any


@dataclass(frozen=True)
class AlignedNodes:
    """Buendelt drei anhand ihrer Listenposition ausgerichtete Knoten."""

    assignment: dict[str, Any]
    student_solution: dict[str, Any]
    reference_solution: dict[str, Any] | None


@dataclass(frozen=True)
class TraversalState:
    """Beschreibt Position, Vorfahren und Anzeigenamen der Rekursion."""

    parent_path: tuple[int, ...] = ()
    assignment_ancestors: tuple[dict[str, Any], ...] = ()
    student_ancestors: tuple[dict[str, Any], ...] = ()
    reference_ancestors: tuple[dict[str, Any], ...] = ()
    labels: tuple[str, ...] = ()


@dataclass
class UnitCollection:
    """Sammelt Bewertungseinheiten und stellt die Rubrics nach Pfad bereit."""

    rubric_map: dict[str, dict[str, Any]]
    units: list[GradingUnit]


def build_grading_units(
    assignment: dict[str, Any],
    student_solution: dict[str, Any],
    *,
    reference_solution: dict[str, Any] | None = None,
    rubrics: dict[str, Any] | None = None,
) -> list[GradingUnit]:
    """Erzeugt Bewertungseinheiten aus parallelen Dokumentbäumen."""

    rubric_map = build_rubric_map(rubrics)
    units: list[GradingUnit] = []
    compare_node_lists(
        ParallelNodeLists(
            assignment=assignment.get("tasks"),
            student_solution=student_solution.get("tasks"),
            reference_solution=(
                reference_solution.get("tasks")
                if reference_solution is not None
                else None
            ),
        ),
        TraversalState(),
        UnitCollection(
            rubric_map=rubric_map,
            units=units,
        ),
    )
    if not units:
        raise ValueError("Die Dokumente enthalten keine bewertbaren Blattknoten.")
    unknown_rubrics = sorted(set(rubric_map) - {unit.path_string for unit in units})
    if unknown_rubrics:
        raise ValueError(
            "Rubrics verweisen auf unbekannte Blattpfade: "
            + ", ".join(unknown_rubrics)
        )
    return units


def compare_node_lists(
    node_lists: ParallelNodeLists,
    state: TraversalState,
    collection: UnitCollection,
) -> None:
    """Vergleicht eine Rekursionsebene und sammelt ihre Blattziele."""

    location = (
        "tasks"
        if not state.parent_path
        else structural_path(state.parent_path) + ".subtasks"
    )
    for index, nodes in enumerate(align_node_lists(node_lists, location)):
        path = (*state.parent_path, index)
        path_string = structural_path(path)
        label = node_label(nodes.assignment, path_string)
        next_labels = (*state.labels, label)
        children = aligned_children(nodes, path_string)
        if children is not None:
            compare_node_lists(
                children,
                TraversalState(
                    parent_path=path,
                    assignment_ancestors=(
                        *state.assignment_ancestors,
                        nodes.assignment,
                    ),
                    student_ancestors=(
                        *state.student_ancestors,
                        nodes.student_solution,
                    ),
                    reference_ancestors=(
                        (*state.reference_ancestors, nodes.reference_solution)
                        if nodes.reference_solution is not None
                        else ()
                    ),
                    labels=next_labels,
                ),
                collection,
            )
            continue
        collection.units.append(
            build_grading_unit(
                nodes=nodes,
                state=state,
                path=path,
                labels=next_labels,
                rubric=collection.rubric_map.get(path_string),
            )
        )


def align_node_lists(
    node_lists: ParallelNodeLists,
    location: str,
) -> list[AlignedNodes]:
    """Validiert parallele Listen und richtet ihre Knoten positionsweise aus."""

    assignment = required_node_list(
        node_lists.assignment, location, "Aufgabenstellung"
    )
    student_solution = required_node_list(
        node_lists.student_solution, location, "Studentische Loesung"
    )
    ensure_matching_node_count(
        assignment,
        student_solution,
        location=location,
        counterpart_label="studentische Loesung",
    )
    reference_solution: list[dict[str, Any]] | None = None
    if node_lists.reference_solution is not None:
        reference_solution = required_node_list(
            node_lists.reference_solution, location, "Musterloesung"
        )
        ensure_matching_node_count(
            assignment,
            reference_solution,
            location=location,
            counterpart_label="Musterloesung",
        )
    return [
        AlignedNodes(
            assignment=assignment_node,
            student_solution=student_solution[index],
            reference_solution=(
                reference_solution[index]
                if reference_solution is not None
                else None
            ),
        )
        for index, assignment_node in enumerate(assignment)
    ]


def ensure_matching_node_count(
    assignment: list[dict[str, Any]],
    counterpart: list[dict[str, Any]],
    *,
    location: str,
    counterpart_label: str,
) -> None:
    """Weist unterschiedliche Knotenzahlen zweier paralleler Listen zurueck."""

    if len(assignment) != len(counterpart):
        raise ValueError(
            f"Strukturabweichung bei {location}: Aufgabenstellung={len(assignment)}, "
            f"{counterpart_label}={len(counterpart)} Knoten."
        )


def aligned_children(
    nodes: AlignedNodes,
    path_string: str,
) -> ParallelNodeLists | None:
    """Prueft die Knotentypen und liefert ausgerichtete Kinder eines Elternknotens."""

    assignment = child_nodes(nodes.assignment, f"Aufgabenstellung: {path_string}")
    student_solution = child_nodes(
        nodes.student_solution, f"Studentische Loesung: {path_string}"
    )
    reference_solution = (
        child_nodes(nodes.reference_solution, f"Musterloesung: {path_string}")
        if nodes.reference_solution is not None
        else None
    )
    ensure_matching_node_kind(
        assignment,
        student_solution,
        path_string=path_string,
        counterpart_label="studentischer Loesung",
    )
    if reference_solution is not None:
        ensure_matching_node_kind(
            assignment,
            reference_solution,
            path_string=path_string,
            counterpart_label="Musterloesung",
        )
    if not assignment:
        return None
    return ParallelNodeLists(
        assignment=assignment,
        student_solution=student_solution,
        reference_solution=reference_solution,
    )


def ensure_matching_node_kind(
    assignment_children: list[dict[str, Any]],
    counterpart_children: list[dict[str, Any]],
    *,
    path_string: str,
    counterpart_label: str,
) -> None:
    """Prueft, ob zwei ausgerichtete Knoten beide Blatt oder Elternknoten sind."""

    if bool(assignment_children) != bool(counterpart_children):
        raise ValueError(
            f"Strukturabweichung bei {path_string}: Blatt-/Elternknoten "
            f"stimmen zwischen Aufgabenstellung und {counterpart_label} nicht ueberein."
        )


def build_grading_unit(
    *,
    nodes: AlignedNodes,
    state: TraversalState,
    path: tuple[int, ...],
    labels: tuple[str, ...],
    rubric: dict[str, Any] | None,
) -> GradingUnit:
    """Erzeugt aus einem ausgerichteten Blatt eine Bewertungseinheit."""

    path_string = structural_path(path)
    try:
        max_points = parse_optional_positive_points(
            nodes.assignment.get("points"),
            location=f"{path_string}.points",
        )
    except ValueError:
        max_points = None
    return GradingUnit(
        path=path,
        path_string=path_string,
        display_label=" / ".join(labels),
        max_points=max_points,
        assignment_node=nodes.assignment,
        assignment_context=ancestor_context(state.assignment_ancestors),
        student_solution_node=nodes.student_solution,
        student_solution_context=ancestor_context(state.student_ancestors),
        reference_solution_node=nodes.reference_solution,
        reference_solution_context=ancestor_context(state.reference_ancestors),
        rubric=rubric,
    )


def required_node_list(value: Any, location: str, label: str) -> list[dict[str, Any]]:
    """Validiert und typisiert eine Liste kanonischer Dokumentknoten."""

    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{label}: {location} ist keine gueltige Knotenliste.")
    return value


def ancestor_context(nodes: tuple[dict[str, Any], ...]) -> str:
    """Fuegt die kontextgebenden Markdown-Felder aller Vorfahren zusammen."""

    return "\n\n".join(
        content
        for node in nodes
        if (content := joined_node_text(
            node, ("introduction_markdown", "markdown", "closing_markdown")
        ))
    )


def build_rubric_map(data: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Indiziert Rubrics nach Zielpfad und weist doppelte Pfade zurueck."""

    if data is None:
        return {}
    raw_rubrics = data.get("rubrics")
    if not isinstance(raw_rubrics, list):
        raise ValueError("Das Rubric-Dokument enthaelt keine rubrics-Liste.")
    result: dict[str, dict[str, Any]] = {}
    for index, rubric in enumerate(raw_rubrics):
        if not isinstance(rubric, dict):
            raise ValueError(f"rubrics[{index}] ist kein JSON-Objekt.")
        target_path = rubric.get("target_path")
        if not isinstance(target_path, str) or not target_path.strip():
            raise ValueError(f"rubrics[{index}].target_path ist ungueltig.")
        if target_path in result:
            raise ValueError(f"Doppelte Rubric fuer {target_path}.")
        result[target_path] = rubric
    return result
