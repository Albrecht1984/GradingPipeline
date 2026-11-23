"""Gemeinsame JSON-Ein- und Ausgabe mit klarer Fehlersemantik."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping


@dataclass(frozen=True)
class LoadedJsonObject:
    """Enthaelt ein geparstes JSON-Objekt und seinen unveraenderten Quelltext."""

    data: dict[str, Any]
    content: str


def read_cache_json_object(path: Path) -> dict[str, Any] | None:
    """Liest ein Cache-Objekt oder behandelt unbrauchbare Daten als Cache-Miss."""

    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def read_required_json_object(path: Path, *, label: str) -> dict[str, Any]:
    """Liest ein erforderliches JSON-Objekt und meldet die genaue Fehlerursache."""

    return read_required_json_document(path, label=label).data


def read_required_json_document(path: Path, *, label: str) -> LoadedJsonObject:
    """Liest ein erforderliches JSON-Objekt samt unveraendertem Quelltext."""

    if not path.is_file():
        raise FileNotFoundError(f"{label} nicht gefunden: {path}")
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OSError(f"{label} kann nicht gelesen werden: {path}: {exc}") from exc
    if not content.strip():
        raise ValueError(f"{label} ist leer: {path}")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} enthaelt ungueltiges JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} ist kein JSON-Objekt: {path}")
    return LoadedJsonObject(data=data, content=content)


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Schreibt ein eingeruecktes, standardkonformes JSON-Objekt."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    """Schreibt Standard-JSON atomar und entfernt temporaere Dateien bei Fehlern."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(
                data,
                temporary,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            temporary.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
