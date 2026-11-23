"""Cache-Verwaltung fuer einzeln partitionierte Hauptaufgaben."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from grading_pipeline.infrastructure.json_io import read_required_json_object


def partition_cache_model(identity: Mapping[str, Any]) -> dict[str, Any]:
    """Beschränkt die Modellidentität auf die Merkmale des Partitionierungscaches."""
    return {
        key: value for key, value in identity.items()
        if key not in {"base_url", "response_format"}
    }


def partition_cache_records(
    cache: dict[str, Any] | None,
    identity: Mapping[str, Any],
) -> dict[tuple[int, str], dict[str, Any]]:
    """Prueft den Partitionierungscache und indiziert seine Hauptaufgaben."""

    if cache is None:
        return {}
    stored_model = cache.get("model")
    if not isinstance(stored_model, dict) or stored_model != identity:
        return {}
    records = cache.get("tasks")
    if not isinstance(records, list):
        return {}
    return {
        (record["index"], record["input_sha256"]): record
        for record in records
        if isinstance(record, dict)
        and isinstance(record.get("index"), int)
        and isinstance(record.get("input_sha256"), str)
    }


def load_partitioned_task(
    *,
    record: dict[str, Any] | None,
    raw_json_path: Path,
    validator: Callable[[dict[str, Any]], None],
) -> dict[str, Any] | None:
    """Laedt genau eine weiterhin gueltige partitionierte Hauptaufgabe."""

    if record is None or not raw_json_path.is_file():
        return None
    data = read_required_json_object(
        raw_json_path, label="Partitionierte Hauptaufgabe"
    )
    validator(data)
    tasks = data["tasks"]
    if len(tasks) != 1:
        raise ValueError(
            "Das Partitionsartefakt muss genau eine Hauptaufgabe enthalten."
        )
    return tasks[0]
