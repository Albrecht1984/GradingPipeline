"""Gemeinsame Hilfstypen und Dateifunktionen für Pipeline-Artefakte."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil

@dataclass(frozen=True)
class ContextMaterial:
    """Repräsentiert eine geladene Kontextdatei samt Herkunft und Inhalt."""

    path: Path
    content: str


@dataclass(frozen=True)
class ModelCallArtifacts:
    """Bündelt die vier Artefakte eines zielweisen Modellaufrufs."""

    input: Path
    raw: Path
    response: Path
    statistics: Path


def preferred_reviewed_artifact(
    directory: Path,
    *,
    raw_filename: str,
    reviewed_filename: str,
) -> Path:
    """Bevorzugt ein vorhandenes Reviewed-Artefakt, sonst das Raw-Artefakt."""

    reviewed_path = directory / reviewed_filename
    return reviewed_path if reviewed_path.is_file() else directory / raw_filename


def read_context_material(paths: list[Path]) -> list[ContextMaterial]:
    """Lädt nicht leere Kontextdateien und versieht sie mit einem Inhalts-Hash."""

    result: list[ContextMaterial] = []
    for supplied_path in paths:
        path = supplied_path.resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Kontextdatei nicht gefunden: {path}")
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError(f"Kontextdatei ist leer: {path}")
        result.append(ContextMaterial(path=path, content=content))
    return result


def filename_stem(
    index: int,
    display_label: str,
    *,
    fallback: str,
    index_width: int = 3,
) -> str:
    """Erzeugt einen sortierbaren, dateisystemtauglichen Artefaktnamen."""

    label = re.sub(r"[^a-zA-Z0-9_.-]+", "_", display_label).strip("_")
    return f"{index:0{index_width}d}_{label or fallback}"


def model_call_artifacts(
    input_dir: Path,
    response_dir: Path,
    stem: str,
) -> ModelCallArtifacts:
    """Leitet die Artefaktpfade eines zielweisen Modellaufrufs ab."""

    return ModelCallArtifacts(
        input=input_dir / f"{stem}.input.md",
        raw=response_dir / f"{stem}.raw.json",
        response=response_dir / f"{stem}.response.json",
        statistics=response_dir / f"{stem}.statistics.json",
    )


def prepare_model_output(
    root: Path,
    *,
    working_dirs: tuple[Path, ...],
    result_files: tuple[Path, ...],
    cache_file: Path,
    preserve_cache: bool,
) -> None:
    """Bereitet die gemeinsamen Ausgabeziele einer zielweisen Modellstufe vor."""

    if root.exists() and not root.is_dir():
        raise NotADirectoryError(f"Der Ausgabepfad ist kein Ordner: {root}")
    root.mkdir(parents=True, exist_ok=True)
    if not preserve_cache:
        for directory in working_dirs:
            if directory.is_dir():
                shutil.rmtree(directory)
        cache_file.unlink(missing_ok=True)
    for path in result_files:
        path.unlink(missing_ok=True)
    for directory in working_dirs:
        directory.mkdir(parents=True, exist_ok=True)
