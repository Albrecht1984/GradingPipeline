"""Provider- und pipelineunabhaengige Cache-Grundfunktionen."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, TypeVar

from grading_pipeline.infrastructure.json_io import (
    read_cache_json_object,
    read_required_json_object,
    write_json_atomic,
)


T = TypeVar("T")


def cache_document_matches(
    cache: dict[str, Any] | None,
    *,
    metadata: Mapping[str, Any],
) -> bool:
    """Prüft, ob alle erwarteten Cache-Metadaten vorliegen und übereinstimmen."""

    return cache is not None and all(
        key in cache and cache[key] == value for key, value in metadata.items()
    )


def read_matching_cache(
    path: Path,
    *,
    metadata: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Liest ein Cache-Dokument mit passenden Metadaten."""

    cache = read_cache_json_object(path)
    if cache_document_matches(cache, metadata=metadata):
        return cache
    return None


def write_cache_document(
    path: Path,
    *,
    metadata: Mapping[str, Any],
) -> None:
    """Schreibt die Metadaten eines Cache-Dokuments atomar."""

    write_json_atomic(path, dict(metadata))


def load_cached_raw_result(
    *,
    cache_available: bool,
    input_path: Path,
    expected_input: str,
    raw_path: Path,
    label: str,
    validator: Callable[[dict[str, Any]], T],
) -> T | None:
    """Lädt ein editierbares Raw-Ergebnis bei unverändertem Modellinput."""

    if not cache_available or not input_path.is_file() or not raw_path.is_file():
        return None
    try:
        stored_input = input_path.read_text(encoding="utf-8")
    except OSError:
        return None
    if stored_input != expected_input.rstrip() + "\n":
        return None
    data = read_required_json_object(raw_path, label=label)
    return validator(data)
