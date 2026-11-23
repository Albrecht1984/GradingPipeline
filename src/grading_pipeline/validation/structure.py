"""Erkennt nicht blockierende Qualitätsprobleme in Aufgabenstrukturen."""

from __future__ import annotations

import re
from typing import Any, Callable

from grading_pipeline.infrastructure.task_nodes import node_text, structural_path
from .numbers import is_finite_number


TECHNICAL_TASK_ID = re.compile(r"^task_\d+$", re.IGNORECASE)
TECHNICAL_SUBTASK_ID = re.compile(r"^subtask_\d+$", re.IGNORECASE)
VISIBLE_SUBTASK_PREFIX = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\([A-Za-z0-9ivxIVX]+\)|"
    r"[A-Za-z0-9ivxIVX]+[.)])(?:\s|$)"
)


def warn_ids(
    document: dict[str, Any], document_type: str, *, warn: Callable[[str], None],
) -> None:
    """Meldet technische IDs und wiederholte Kennzeichnungen direkt über warn."""
    def visit(nodes: Any, parent_path: tuple[int, ...]) -> None:
        """Durchläuft Aufgaben rekursiv und gibt jeden erkannten Hinweis sofort aus."""
        if not isinstance(nodes, list):
            return
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                continue
            path = (*parent_path, index)
            _warn_node_id(node, path=path, document_type=document_type, warn=warn)
            visit(node.get("subtasks"), path)

    visit(document.get("tasks"), ())


def _warn_node_id(
    node: dict[str, Any], *, path: tuple[int, ...],
    document_type: str, warn: Callable[[str], None],
) -> None:
    """Prüft die Kennzeichnungen eines Knotens, ohne Texte oder Metadaten zu ändern."""
    path_string = structural_path(path)
    node_id = node_text(node, "id").strip()
    source_label = node_text(node, "source_label").strip()
    prefix = f"WARNUNG: {document_type} {path_string}"
    if (len(path) == 1 and TECHNICAL_TASK_ID.fullmatch(node_id)
            and source_label):
        warn(f"{prefix} verwendet die technische ID {node_id!r}, obwohl die sichtbare "
             f"Kennzeichnung {source_label!r} vorliegt.")
    markdown = node_text(node, "markdown")
    if len(path) <= 1 or not markdown:
        return
    repeated_label = repeated_subtask_label(markdown, node_id)
    if repeated_label is not None:
        warn(f"{prefix} wiederholt die bereits in id gespeicherte Bezeichnung "
             f"{node_id!r} am Anfang des Markdown-Inhalts.")
    repeated_points = repeated_subtask_points(markdown, node.get("points"))
    if repeated_points is not None:
        warn(f"{prefix} wiederholt die bereits in points gespeicherte Punktzahl "
             f"{node.get('points')!r} am Ende des Markdown-Inhalts als {repeated_points!r}.")
    visible_prefix = VISIBLE_SUBTASK_PREFIX.match(markdown)
    if (TECHNICAL_SUBTASK_ID.fullmatch(node_id) and visible_prefix is not None
            and repeated_label is None):
        warn(f"{prefix} verwendet die technische ID {node_id!r}, obwohl der Inhalt "
             f"mit der sichtbaren Kennzeichnung {visible_prefix.group(0).strip()!r} beginnt.")

def repeated_subtask_label(markdown: str, subtask_id: str) -> str | None:
    """Erkennt eine bereits in ``id`` gespeicherte Kennzeichnung am Textanfang."""
    if not subtask_id:
        return None
    escaped_id = re.escape(subtask_id)
    pattern = re.compile(
        rf"^\s*(?:#{{1,6}}\s*)?(?:\*\*|__)?"
        rf"(?:\(\s*{escaped_id}\s*\)|{escaped_id}\s*[.)])"
        rf"(?:\*\*|__)?(?:\s|&emsp;)*",
        re.IGNORECASE,
    )
    match = pattern.match(markdown)
    return match.group(0) if match is not None else None


def repeated_subtask_points(markdown: str, points: Any) -> str | None:
    """Erkennt eine bereits strukturierte Punktzahl am Ende des Markdown-Texts."""
    if not is_finite_number(points):
        return None
    numeric = f"{float(points):g}"
    variants = {numeric, numeric.replace(".", ",")}
    if float(points).is_integer():
        integer = str(int(points))
        variants.update({integer, f"{integer}.0", f"{integer},0"})
    number_pattern = "|".join(
        re.escape(item) for item in sorted(variants, key=len, reverse=True)
    )
    pattern = re.compile(
        rf"(?:\*\*|__)?(?:{number_pattern})\s*Punkt(?:e)?"
        rf"(?:\*\*|__)?[.\s]*$",
        re.IGNORECASE,
    )
    match = pattern.search(markdown)
    return match.group(0).strip() if match is not None else None
