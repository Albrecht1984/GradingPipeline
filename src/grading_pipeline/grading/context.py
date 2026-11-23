"""Laedt und validiert aufgabenspezifisches Kontextmaterial fuer das Grading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from grading_pipeline.infrastructure.json_io import read_required_json_object
from grading_pipeline.infrastructure.pipeline_artifacts import (
    ContextMaterial,
    read_context_material,
)


@dataclass(frozen=True)
class LoadedTaskContextMap:
    """Buendelt Manifestpfad und Kontextdateien nach strukturellem Zielpfad."""

    path: Path
    by_target_path: dict[str, list[ContextMaterial]]


def read_task_context_map(
    supplied_path: Path,
    *,
    expected_target_paths: list[str],
) -> LoadedTaskContextMap:
    """Laedt eine vollstaendige, eindeutige Kontextzuordnung fuer Blattaufgaben."""

    path = supplied_path.resolve()
    data = read_required_json_object(path, label="Grading-Kontextmanifest")
    raw_contexts = data.get("contexts")
    if not isinstance(raw_contexts, list):
        raise ValueError("Grading-Kontextmanifest enthaelt keine contexts-Liste.")

    manifest_dir = path.parent.resolve()
    by_target_path: dict[str, list[ContextMaterial]] = {}
    for index, raw_entry in enumerate(raw_contexts):
        target_path, relative_files = _parse_context_entry(raw_entry, index=index)
        if target_path in by_target_path:
            raise ValueError(
                f"Doppelter target_path im Grading-Kontextmanifest: {target_path}."
            )
        resolved_files = [
            _resolve_context_file(relative_file, manifest_dir=manifest_dir)
            for relative_file in relative_files
        ]
        by_target_path[target_path] = read_context_material(resolved_files)

    _validate_target_paths(
        by_target_path,
        expected_target_paths=expected_target_paths,
    )
    return LoadedTaskContextMap(path=path, by_target_path=by_target_path)


def _parse_context_entry(raw_entry: Any, *, index: int) -> tuple[str, list[str]]:
    """Validiert einen einzelnen Eintrag des Kontextmanifests."""

    if not isinstance(raw_entry, dict):
        raise ValueError(f"contexts[{index}] ist kein JSON-Objekt.")
    target_path = raw_entry.get("target_path")
    if not isinstance(target_path, str) or not target_path.strip():
        raise ValueError(f"contexts[{index}].target_path ist ungueltig.")
    raw_files = raw_entry.get("files")
    if not isinstance(raw_files, list) or any(
        not isinstance(value, str) or not value.strip()
        for value in raw_files
    ):
        raise ValueError(
            f"contexts[{index}].files muss eine Liste nichtleerer Pfade sein."
        )
    relative_files = [value.strip() for value in raw_files]
    if len(relative_files) != len(set(relative_files)):
        raise ValueError(f"contexts[{index}].files enthaelt doppelte Pfade.")
    return target_path.strip(), relative_files


def _resolve_context_file(relative_file: str, *, manifest_dir: Path) -> Path:
    """Loest einen relativen Kontextpfad sicher innerhalb des Manifestordners auf."""

    supplied = Path(relative_file)
    if supplied.is_absolute():
        raise ValueError(
            "Kontextdateien im Grading-Kontextmanifest muessen relativ sein: "
            f"{relative_file}"
        )
    path = (manifest_dir / supplied).resolve()
    if path == manifest_dir or not path.is_relative_to(manifest_dir):
        raise ValueError(
            "Kontextdatei liegt ausserhalb des Manifestordners: "
            f"{relative_file}"
        )
    return path


def _validate_target_paths(
    by_target_path: dict[str, list[ContextMaterial]],
    *,
    expected_target_paths: list[str],
) -> None:
    """Fordert genau einen Manifesteintrag fuer jede bewertbare Blattaufgabe."""

    expected = set(expected_target_paths)
    actual = set(by_target_path)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append("fehlend: " + ", ".join(missing))
        if unknown:
            details.append("unbekannt: " + ", ".join(unknown))
        raise ValueError(
            "Grading-Kontextmanifest passt nicht zu den Blattaufgaben ("
            + "; ".join(details)
            + ")."
        )
