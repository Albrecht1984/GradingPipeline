"""Zentrale, unveränderliche Dateinamen aller erzeugten Pipeline-Artefakte."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VisualExtractionArtifactNames:
    """Benennt die Artefakte der visuellen Extraktion."""

    pages_dir: str = "01_pages"
    responses_dir: str = "02_page_responses"
    markdown: str = "03_vlm_export.raw.md"
    reviewed_markdown: str = "03_vlm_export.reviewed.md"
    document_json: str = "03_vlm_document.raw.json"


@dataclass(frozen=True, slots=True)
class TaskExtractionArtifactNames:
    """Benennt die Artefakte der Aufgabenextraktion."""

    source: str
    input_markdown: str
    raw_json: str
    reviewed_json: str
    response_json: str
    cache_json: str
    statistics_json: str
    tasks_dir: str
    export_markdown: str


@dataclass(frozen=True, slots=True)
class TaskPartitioningArtifactNames:
    """Benennt die Artefakte der Aufgabenpartitionierung."""

    source: str
    input_markdown: str
    responses_dir: str
    raw_json: str
    reviewed_json: str
    cache_json: str
    tasks_dir: str
    export_markdown: str


@dataclass(frozen=True, slots=True)
class RubricArtifactNames:
    """Benennt Eingaben, Antworten und Exporte der Rubric-Erzeugung."""

    partitioned_document: str = "06_task_partitioning.raw.json"
    structure_check: str = "01_structure_check.json"
    inputs_dir: str = "02_rubric_inputs"
    responses_dir: str = "02_rubric_responses"
    raw_json: str = "02_rubrics.raw.json"
    reviewed_json: str = "02_rubrics.reviewed.json"
    cache_json: str = "02_rubrics.cache.json"
    export_markdown: str = "03_rubrics_export.md"


@dataclass(frozen=True, slots=True)
class GradingArtifactNames:
    """Benennt Strukturprüfung, Modellausgaben und Bewertungsberichte."""

    structure_check: str = "01_structure_check.json"
    inputs_dir: str = "02_grading_inputs"
    responses_dir: str = "02_grading_responses"
    results_json: str = "03_grading_results.raw.json"
    cache_json: str = "03_grading.cache.json"
    report_markdown: str = "04_grading_report.md"
    feedback_markdown: str = "05_student_feedback.md"


VISUAL_EXTRACTION_ARTIFACTS = VisualExtractionArtifactNames()
TASK_EXTRACTION_ARTIFACTS = TaskExtractionArtifactNames(
    source=VISUAL_EXTRACTION_ARTIFACTS.markdown,
    input_markdown="04_task_extraction.input.md",
    raw_json="04_task_extraction.raw.json",
    reviewed_json="04_task_extraction.reviewed.json",
    response_json="04_task_extraction.response.json",
    cache_json="04_task_extraction.cache.json",
    statistics_json="04_task_extraction.statistics.json",
    tasks_dir="05_tasks",
    export_markdown="05_tasks_export.md",
)
TASK_PARTITIONING_ARTIFACTS = TaskPartitioningArtifactNames(
    source=TASK_EXTRACTION_ARTIFACTS.raw_json,
    input_markdown="06_task_partitioning.input.md",
    responses_dir="06_task_partitioning_responses",
    raw_json="06_task_partitioning.raw.json",
    reviewed_json="06_task_partitioning.reviewed.json",
    cache_json="06_task_partitioning.cache.json",
    tasks_dir="07_partitioned_tasks",
    export_markdown="07_partitioned_tasks_export.md",
)
RUBRIC_ARTIFACTS = RubricArtifactNames()
GRADING_ARTIFACTS = GradingArtifactNames()
