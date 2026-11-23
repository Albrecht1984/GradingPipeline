"""Prüft vorhandene Pipeline-Artefakte eines Ordners ohne sie zu verändern."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any, Callable, Literal

from grading_pipeline.grading.validation import validate_grading_response
from grading_pipeline.infrastructure.artifact_names import (
    GRADING_ARTIFACTS,
    RUBRIC_ARTIFACTS,
    TASK_EXTRACTION_ARTIFACTS,
    TASK_PARTITIONING_ARTIFACTS,
    VISUAL_EXTRACTION_ARTIFACTS,
)
from grading_pipeline.infrastructure.json_io import read_required_json_document
from grading_pipeline.infrastructure.pipeline_artifacts import preferred_reviewed_artifact
from grading_pipeline.infrastructure.task_nodes import child_nodes, structural_path
from grading_pipeline.rubrics.validation import validate_rubric
from .numbers import parse_optional_positive_points, same_number
from .tasks import (
    validate_partitioned_tasks,
    validate_preserved_task_metadata,
    validate_tasks,
    warn_extraction_content,
)


IssueKind = Literal["required", "quality"]
_PAGE_MARKER = re.compile(r"<!--\s*Seite\s+\d+\s*-->", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """Beschreibt einen technischen Fehler oder einen Qualitätshinweis."""

    kind: IssueKind
    artifact: str
    message: str
    location: str | None = None

    def to_dict(self) -> dict[str, str]:
        """Serialisiert den Fund ohne leere Ortsangabe."""
        data = {"kind": self.kind, "artifact": self.artifact, "message": self.message}
        if self.location is not None:
            data["location"] = self.location
        return data


@dataclass(slots=True)
class ArtifactValidationReport:
    """Sammelt alle Funde einer unverändernden Ordnerprüfung."""

    directory: Path
    checked_artifacts: list[str] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def required_issues(self) -> list[ValidationIssue]:
        """Liefert alle technisch blockierenden Funde."""
        return [issue for issue in self.issues if issue.kind == "required"]

    @property
    def quality_issues(self) -> list[ValidationIssue]:
        """Liefert alle nicht blockierenden Qualitätsfunde."""
        return [issue for issue in self.issues if issue.kind == "quality"]

    @property
    def status(self) -> str:
        """Liefert invalid, warnings oder valid entsprechend den Funden."""
        return "invalid" if self.required_issues else "warnings" if self.issues else "valid"

    def add(
        self, kind: IssueKind, artifact: str, message: str,
        location: str | None = None,
    ) -> None:
        """Erfasst einen technischen oder qualitativen Fund."""
        self.issues.append(ValidationIssue(
            kind, artifact, message.removeprefix("WARNUNG: "), location
        ))

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert Ergebnis, Zählwerte und sämtliche Funde."""
        required, quality = self.required_issues, self.quality_issues
        return {
            "status": self.status,
            "directory": str(self.directory),
            "checked_artifacts": self.checked_artifacts,
            "required_issue_count": len(required),
            "quality_issue_count": len(quality),
            "required_issues": [issue.to_dict() for issue in required],
            "quality_issues": [issue.to_dict() for issue in quality],
        }


def validate_artifact_directory(directory: Path) -> ArtifactValidationReport:
    """Prüft alle erkannten Endartefakte in ``directory`` und liefert die Befunde."""
    root = directory.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Artefakt-Ordner nicht gefunden: {root}")
    report = ArtifactValidationReport(root)
    _validate_visual(report)
    extraction_filename = preferred_reviewed_artifact(
        root,
        raw_filename=TASK_EXTRACTION_ARTIFACTS.raw_json,
        reviewed_filename=TASK_EXTRACTION_ARTIFACTS.reviewed_json,
    ).name
    extracted = _validate_tasks(report, extraction_filename, False)
    partition_filename = preferred_reviewed_artifact(
        root,
        raw_filename=TASK_PARTITIONING_ARTIFACTS.raw_json,
        reviewed_filename=TASK_PARTITIONING_ARTIFACTS.reviewed_json,
    ).name
    partitioned = _validate_tasks(report, partition_filename, True)
    if extracted is not None and partitioned is not None:
        _compare_tasks(report, extracted, partitioned, artifact=partition_filename)
    _validate_rubrics(report)
    _validate_gradings(report)
    if not report.checked_artifacts:
        report.add("required", ".", "Der Ordner enthält kein bekanntes prüfbares GradingPipeline-Artefakt.")
    return report


def _warn(report: ArtifactValidationReport, artifact: str, location: str | None = None):
    """Erzeugt einen Empfänger für wiederverwendete Qualitätsprüfungen."""
    return lambda message: report.add("quality", artifact, message, location)


def _validate_visual(report: ArtifactValidationReport) -> None:
    """Prüft zusammengeführten Seitentext und vorhandene Einzelseiten."""
    path = preferred_reviewed_artifact(
        report.directory,
        raw_filename=VISUAL_EXTRACTION_ARTIFACTS.markdown,
        reviewed_filename=VISUAL_EXTRACTION_ARTIFACTS.reviewed_markdown,
    )
    if path.is_file():
        report.checked_artifacts.append(path.name)
        content = _read_text(report, path, path.name)
        if content is not None and not _PAGE_MARKER.sub("", content).strip():
            report.add("required", path.name, "Der zusammengeführte Seitentext ist leer.")
    responses = report.directory / VISUAL_EXTRACTION_ARTIFACTS.responses_dir
    if responses.is_dir():
        for path in sorted(responses.glob("page_*.raw.md")):
            artifact = str(path.relative_to(report.directory))
            content = _read_text(report, path, artifact)
            if content is not None and not content.strip():
                report.add("quality", artifact, "Der extrahierte Seitentext ist leer.")


def _read_text(
    report: ArtifactValidationReport, path: Path, artifact: str
) -> str | None:
    """Liest Text und erfasst einen technischen Lesefehler."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        report.add("required", artifact, f"Datei kann nicht gelesen werden: {exc}")
        return None


def _validate_tasks(
    report: ArtifactValidationReport, filename: str, partitioned: bool
) -> dict[str, Any] | None:
    """Prüft ein vorhandenes Aufgabenartefakt."""
    data = _read_json(report, filename)
    if data is None:
        return None
    try:
        validator = validate_partitioned_tasks if partitioned else validate_tasks
        validator(data, warn=_warn(report, filename))
    except ValueError as exc:
        report.add("required", filename, str(exc))
        return None
    warn_extraction_content(data, warn=_warn(report, filename))
    if partitioned and data["document_type"] == "assignment":
        _warn_points(data, warn=_warn(report, filename))
    return data


def _compare_tasks(
    report: ArtifactValidationReport,
    extracted: dict[str, Any],
    partitioned: dict[str, Any],
    *,
    artifact: str,
) -> None:
    """Vergleicht Metadaten und Anzahl vor und nach der Partitionierung."""
    if extracted["document_type"] != partitioned["document_type"]:
        report.add(
            "required", artifact,
            "Der Dokumenttyp stimmt nicht mit der Aufgabenextraktion überein: "
            f"{extracted['document_type']!r} statt {partitioned['document_type']!r}.",
            "document_type",
        )
    source, result = extracted["tasks"], partitioned["tasks"]
    if len(source) != len(result):
        report.add(
            "required", artifact,
            f"Die Zahl der Hauptaufgaben wurde verändert: {len(source)} statt {len(result)}.",
            "tasks",
        )
    for index, (before, after) in enumerate(zip(source, result), start=1):
        validate_preserved_task_metadata(
            before, after, location=f"Hauptaufgabe {index}",
            warn=_warn(report, artifact),
        )


def _warn_points(document: dict[str, Any], *, warn: Callable[[str], None]) -> None:
    """Meldet fehlende Blattpunkte und abweichende Elternsummen."""
    def visit(node: dict[str, Any], path: tuple[int, ...]) -> list[tuple[str, float | None]]:
        """Liefert Blätter eines Teilbaums und prüft seine Punktverteilung."""
        location = structural_path(path)
        children = child_nodes(node, location)
        points = _points(node.get("points"), f"{location}.points")
        if not children:
            return [(location, points)]
        leaves = [leaf for index, child in enumerate(children)
                  for leaf in visit(child, (*path, index))]
        missing = sum(value is None for _, value in leaves)
        if points is not None and missing:
            warn(f"WARNUNG: {location} besitzt {points:g} Gesamtpunkte, aber "
                 f"{missing} Blattknoten ohne Teilpunktzahl.")
        elif points is not None:
            total = sum(value for _, value in leaves if value is not None)
            if not same_number(total, points):
                warn(f"WARNUNG: Die Blattpunktzahlen unter {location} ergeben "
                     f"{total:g} statt {points:g} Punkte.")
        return leaves

    leaves = [leaf for index, task in enumerate(document["tasks"])
              for leaf in visit(task, (index,))]
    for path, points in leaves:
        if points is None:
            warn(f"WARNUNG: {path} besitzt keine verwendbare Maximalpunktzahl.")


def _validate_rubrics(report: ArtifactValidationReport) -> None:
    """Prüft ein vorhandenes Rubric-Gesamtergebnis."""
    filename = preferred_reviewed_artifact(
        report.directory,
        raw_filename=RUBRIC_ARTIFACTS.raw_json,
        reviewed_filename=RUBRIC_ARTIFACTS.reviewed_json,
    ).name
    data = _read_json(report, filename)
    if data is None:
        return
    rubrics = data.get("rubrics")
    if not isinstance(rubrics, list):
        report.add("required", filename, "rubrics ist keine Liste.", "rubrics")
        return
    if not rubrics:
        report.add("quality", filename, "Die Rubric-Liste ist leer.", "rubrics")
    seen: set[str] = set()
    for index, rubric in enumerate(rubrics):
        location = f"rubrics[{index}]"
        if not isinstance(rubric, dict):
            report.add("required", filename, "Die Rubric ist kein JSON-Objekt.", location)
            continue
        path = rubric.get("target_path")
        if not isinstance(path, str) or not path.strip():
            report.add("required", filename, "target_path ist kein nichtleerer Text.",
                       f"{location}.target_path")
            continue
        if path in seen:
            report.add("quality", filename, f"Mehrere Rubrics verwenden {path!r}.",
                       f"{location}.target_path")
        seen.add(path)
        _quality_check(
            report, filename, location,
            lambda: validate_rubric(
                rubric,
                SimpleNamespace(path_string=path, max_points=_points(rubric.get("max_points"), "max_points")),
                warn=_warn(report, filename, location),
            ),
        )


def _validate_gradings(report: ArtifactValidationReport) -> None:
    """Prüft ein vorhandenes zusammengeführtes Bewertungsergebnis."""
    filename = GRADING_ARTIFACTS.results_json
    data = _read_json(report, filename)
    if data is None:
        return
    results = data.get("task_results")
    if not isinstance(results, list):
        report.add("required", filename, "task_results ist keine Liste.", "task_results")
        return
    if data.get("graded_task_count") != len(results):
        report.add("quality", filename, "graded_task_count entspricht nicht der Ergebniszahl.",
                   "graded_task_count")
    for index, result in enumerate(results):
        location = f"task_results[{index}]"
        if not isinstance(result, dict):
            report.add("required", filename, "Die Aufgabenbewertung ist kein JSON-Objekt.", location)
            continue
        _quality_check(
            report, filename, location,
            lambda result=result: validate_grading_response(
                result,
                target_path=result.get("target_path") if isinstance(result.get("target_path"), str) else location,
                display_label=result.get("display_label") if isinstance(result.get("display_label"), str) else location,
                expected_max_points=_points(result.get("max_points"), "max_points"),
                warn=_warn(report, filename, location),
            ),
        )
    failed = data.get("failed_tasks")
    if not isinstance(failed, list):
        report.add("quality", filename, "failed_tasks ist keine Liste.", "failed_tasks")
    elif data.get("failed_task_count") != len(failed):
        report.add("quality", filename, "failed_task_count entspricht nicht der Fehlerzahl.",
                   "failed_task_count")


def _quality_check(
    report: ArtifactValidationReport, artifact: str, location: str,
    check: Callable[[], Any],
) -> None:
    """Wandelt ein fachliches Validierungssignal in einen Qualitätshinweis um."""
    try:
        check()
    except ValueError as exc:
        report.add("quality", artifact, str(exc), location)


def _read_json(
    report: ArtifactValidationReport, filename: str
) -> dict[str, Any] | None:
    """Liest ein bekanntes JSON-Artefakt und erfasst Lesefehler."""
    path = report.directory / filename
    if not path.is_file():
        return None
    report.checked_artifacts.append(filename)
    try:
        return read_required_json_document(path, label=filename).data
    except (OSError, ValueError) as exc:
        report.add("required", filename, str(exc))
        return None


def _points(value: Any, location: str) -> float | None:
    """Liest verwendbare positive Punkte ohne Fehlersignal."""
    try:
        return parse_optional_positive_points(value, location=location)
    except ValueError:
        return None
