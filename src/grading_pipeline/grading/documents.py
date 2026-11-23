"""Laden und Beschreiben der Quelldokumente für das Grading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from grading_pipeline.infrastructure.artifact_names import (
    RUBRIC_ARTIFACTS,
    TASK_PARTITIONING_ARTIFACTS,
)
from grading_pipeline.infrastructure.json_io import read_required_json_document
from grading_pipeline.infrastructure.pipeline_artifacts import preferred_reviewed_artifact


PARTITION_FILENAME = TASK_PARTITIONING_ARTIFACTS.raw_json
REVIEWED_PARTITION_FILENAME = TASK_PARTITIONING_ARTIFACTS.reviewed_json
RUBRICS_FILENAME = RUBRIC_ARTIFACTS.raw_json
REVIEWED_RUBRICS_FILENAME = RUBRIC_ARTIFACTS.reviewed_json


@dataclass(frozen=True)
class LoadedDocument:
    """Repraesentiert ein geladenes JSON-Dokument samt unveraendertem Inhalt."""

    path: Path
    data: dict[str, Any]
    content: str


def read_partitioned_document(
    directory: Path,
    *,
    expected_type: str,
) -> LoadedDocument:
    """Laedt ein partitioniertes Dokument und prueft Typ und Wurzelstruktur."""

    resolved_directory = directory.resolve()
    path = preferred_reviewed_artifact(
        resolved_directory,
        raw_filename=PARTITION_FILENAME,
        reviewed_filename=REVIEWED_PARTITION_FILENAME,
    )
    loaded = read_json_file(path, "Partitioniertes Dokument")
    if loaded.data.get("document_type") != expected_type:
        raise ValueError(
            f"Falscher document_type in {path}: erwartet {expected_type!r}."
        )
    tasks = loaded.data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError(f"Das Dokument enthaelt keine tasks: {path}")
    return loaded


def read_rubrics(directory: Path) -> LoadedDocument:
    """Laedt das Rubric-Artefakt aus einem Ausgabeverzeichnis."""

    path = preferred_reviewed_artifact(
        directory.resolve(),
        raw_filename=RUBRICS_FILENAME,
        reviewed_filename=REVIEWED_RUBRICS_FILENAME,
    )
    loaded = read_json_file(path, "Rubric-Dokument")
    rubrics = loaded.data.get("rubrics")
    if not isinstance(rubrics, list):
        raise ValueError(f"Das Rubric-Dokument enthaelt keine rubrics-Liste: {path}")
    return loaded


def read_json_file(path: Path, label: str) -> LoadedDocument:
    """Laedt ein erforderliches JSON-Objekt samt unveraendertem Quelltext."""

    loaded = read_required_json_document(path, label=label)
    return LoadedDocument(path=path, data=loaded.data, content=loaded.content)


def source_payload(document: LoadedDocument) -> dict[str, str]:
    """Beschreibt eine Quelle durch ihren Dateinamen."""

    return {"path": document.path.name}
