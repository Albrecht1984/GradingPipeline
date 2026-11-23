"""Stellt gemeinsame Benennungs- und Markdown-Helfer für Aufgabenartefakte bereit."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from grading_pipeline.infrastructure.pipeline_artifacts import filename_stem
from grading_pipeline.infrastructure.task_nodes import text_or_empty

def render_heading(
    task_id: str,
    title: Any,
    points: Any,
    *,
    level: int,
) -> str:
    """Rendert eine Markdown-Überschrift aus ID, Titel und optionalen Punkten."""
    label = task_id.strip()
    title_text = text_or_empty(title).strip()
    if title_text and title_text != label and not label.endswith(title_text):
        label = f"{label} {title_text}"
    if points is not None:
        number = (
            str(points)
            if isinstance(points, int) or not isinstance(points, float)
            else f"{points:g}"
        )
        label = f"{label} — {number} Punkte"
    return f"{'#' * level} {label}"


def task_filename(index: int, task_id: str) -> str:
    """Erzeugt einen sortierbaren und dateisystemtauglichen Aufgabendateinamen."""
    return filename_stem(
        index,
        task_id,
        fallback=f"task_{index:03d}",
        index_width=2,
    ) + ".md"


def write_task_markdown_artifacts(
    tasks: list[dict[str, Any]],
    *,
    tasks_dir: Path,
    export_path: Path,
    render: Callable[[dict[str, Any]], str],
    progress: Callable[[str], None] | None = None,
) -> None:
    """Schreibt einzelne Aufgaben-Markdowns und den gemeinsamen Export."""
    tasks_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[str] = []
    for index, task in enumerate(tasks, start=1):
        markdown = render(task)
        filename = task_filename(index, str(task.get("id", "")))
        (tasks_dir / filename).write_text(markdown + "\n", encoding="utf-8")
        rendered.append(markdown)
        if progress is not None:
            progress(
                f"Aufgabe {index}/{len(tasks)} gespeichert: "
                f"{task.get('id') or task.get('title') or filename}"
            )
    export_path.write_text(
        "\n\n".join(rendered).strip() + "\n",
        encoding="utf-8",
    )
