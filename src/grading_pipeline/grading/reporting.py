"""Erzeugung und Speicherung der lesbaren Bewertungsberichte."""

from __future__ import annotations

from pathlib import Path

from grading_pipeline.infrastructure.artifact_names import GRADING_ARTIFACTS
from .schema import FailedTaskGrading, GradingDocumentResult, TaskGrading


def render_grading_report(result: GradingDocumentResult) -> str:
    """Rendert den vollständigen internen Bewertungsbericht als Markdown."""

    title = "# Bewertungsbericht"
    parts = [title]
    if result.student_id:
        parts.append(f"**Student-ID:** {result.student_id}")
    parts.append(overall_score_text(result))
    for task in result.task_results:
        parts.extend(render_task_report(task))
    for failure in result.failed_tasks:
        parts.extend(render_failed_task_report(failure))
    return "\n\n".join(parts).strip()


def render_student_feedback(result: GradingDocumentResult) -> str:
    """Rendert die für Studierende bestimmte Rückmeldung als Markdown."""

    parts = ["# Feedback zur Abgabe"]
    if result.student_id:
        parts.append(f"**Student-ID:** {result.student_id}")
    if result.points is not None and result.max_points is not None:
        parts.append(
            f"**Gesamtergebnis:** {format_number(result.points)} von "
            f"{format_number(result.max_points)} Punkten"
        )
    for task in result.task_results:
        heading = f"## {task.display_label}"
        if task.points is not None and task.max_points is not None:
            heading += (
                f" — {format_number(task.points)} von "
                f"{format_number(task.max_points)} Punkten"
            )
        else:
            heading += " — qualitative Bewertung"
        parts.extend([heading, task.student_feedback])
    for failure in result.failed_tasks:
        parts.extend(render_failed_task_report(failure))
    return "\n\n".join(parts).strip()


def render_task_report(task: TaskGrading) -> list[str]:
    """Rendert die Abschnitte einer erfolgreichen Aufgabenbewertung."""

    if task.points is None or task.max_points is None:
        heading = f"## {task.display_label} — ohne Punktbewertung"
        score_note = (
            "Für diese Teilaufgabe liegt keine verbindliche Maximalpunktzahl vor. "
            "Daher wurde ausschließlich qualitativ bewertet."
        )
    else:
        heading = (
            f"## {task.display_label} — {format_number(task.points)} von "
            f"{format_number(task.max_points)} Punkten"
        )
        score_note = ""
    parts = [heading]
    if score_note:
        parts.append(score_note)
    for item in task.assessment_items:
        item_heading = f"### {item.description}"
        if item.points is not None and item.max_points is not None:
            item_heading += (
                f" — {format_number(item.points)} von "
                f"{format_number(item.max_points)} Punkten"
            )
        parts.extend([item_heading, item.comment])
    parts.extend(
        [
            f"**Zusammenfassung:** {task.summary}",
            f"**Feedback:** {task.student_feedback}",
        ]
    )
    return parts


def render_failed_task_report(failure: FailedTaskGrading) -> list[str]:
    """Kennzeichnet eine fehlende Bewertung, ohne Validierungsmeldungen zu archivieren."""
    parts = [f"## {failure.display_label} — keine Bewertung"]
    if failure.failure_tag is not None:
        parts.append(f"**Ausfallgrund:** `{failure.failure_tag}`")
    parts.append("Diese Aufgabe wurde nicht bewertet und nicht als null Punkte gewertet.")
    return parts

def overall_score_text(result: GradingDocumentResult) -> str:
    """Formuliert das numerische, qualitative oder unvollständige Gesamtergebnis."""

    if result.failed_tasks:
        return (
            "**Gesamtergebnis:** unvollstaendig, da mindestens eine Aufgabe "
            "nicht formal gueltig bewertet werden konnte."
        )
    if result.points is None or result.max_points is None:
        return (
            "**Gesamtergebnis:** keine vollständige numerische Gesamtpunktzahl, "
            "da mindestens eine Teilaufgabe keine verbindliche Punktgrundlage besitzt."
        )
    return (
        f"**Gesamtergebnis:** {format_number(result.points)} von "
        f"{format_number(result.max_points)} Punkten"
    )


def write_reports(
    result: GradingDocumentResult,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Schreibt Bewertungsbericht und Studierendenfeedback in den Ausgabeordner."""

    report_path = output_dir / GRADING_ARTIFACTS.report_markdown
    feedback_path = output_dir / GRADING_ARTIFACTS.feedback_markdown
    report_path.write_text(render_grading_report(result) + "\n", encoding="utf-8")
    feedback_path.write_text(
        render_student_feedback(result) + "\n", encoding="utf-8"
    )
    return report_path, feedback_path


def format_number(value: float) -> str:
    """Formatiert eine Punktzahl kompakt mit deutschem Dezimaltrennzeichen."""

    return f"{value:g}".replace(".", ",")
