"""Typisierte Ergebnisobjekte der Bewertungspipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from grading_pipeline.infrastructure.result_status import ResultStatus, result_status


@dataclass(frozen=True)
class AssessmentItem:
    """Beschreibt einen vom Modell bewerteten Einzelaspekt einer Aufgabe."""

    id: str
    description: str
    points: float | None
    max_points: float | None
    comment: str

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den Bewertungsaspekt für die JSON-Ausgabe."""

        return {
            "id": self.id,
            "description": self.description,
            "points": self.points,
            "max_points": self.max_points,
            "comment": self.comment,
        }


@dataclass(frozen=True)
class TaskGrading:
    """Enthält die validierte Bewertung einer strukturell bestimmten Blattaufgabe."""

    target_path: str
    display_label: str
    points: float | None
    max_points: float | None
    assessment_items: tuple[AssessmentItem, ...]
    summary: str
    student_feedback: str

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert die Aufgabenbewertung für Ergebnisdateien."""

        return {
            "target_path": self.target_path,
            "display_label": self.display_label,
            "points": self.points,
            "max_points": self.max_points,
            "assessment_items": [item.to_dict() for item in self.assessment_items],
            "summary": self.summary,
            "student_feedback": self.student_feedback,
        }


@dataclass(frozen=True)
class FailedTaskGrading:
    """Kennzeichnet ein nicht bewertetes Ziel samt optionalem Ausfallgrund."""

    target_path: str
    display_label: str
    failure_tag: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den fehlgeschlagenen Bewertungsversuch."""

        payload = {
            "target_path": self.target_path,
            "display_label": self.display_label,
            "status": "failed",
        }
        if self.failure_tag is not None:
            payload["failure_tag"] = self.failure_tag
        return payload


@dataclass(frozen=True)
class GradingDocumentResult:
    """Fasst alle Aufgabenbewertungen einer studentischen Abgabe zusammen."""

    student_id: str | None
    points: float | None
    max_points: float | None
    task_results: tuple[TaskGrading, ...]
    failed_tasks: tuple[FailedTaskGrading, ...] = ()

    @property
    def status(self) -> ResultStatus:
        """Gibt an, ob alle Aufgaben formal gültig bewertet wurden."""

        return result_status(has_failures=bool(self.failed_tasks))

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert das Gesamtergebnis einschließlich Zählwerten und Status."""

        return {
            "status": self.status,
            "student_id": self.student_id,
            "points": self.points,
            "max_points": self.max_points,
            "graded_task_count": len(self.task_results),
            "failed_task_count": len(self.failed_tasks),
            "task_results": [result.to_dict() for result in self.task_results],
            "failed_tasks": [failure.to_dict() for failure in self.failed_tasks],
        }
