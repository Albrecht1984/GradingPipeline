"""Bündelt gemeinsame Abläufe der Aufgabenextraktion und -partitionierung."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Callable

from langchain_core.language_models import BaseChatModel

from grading_pipeline.models.prompts import create_prompt_template
from grading_pipeline.infrastructure.pipeline_artifacts import preferred_reviewed_artifact


@dataclass(frozen=True)
class TaskProcessingResult:
    """Gemeinsame Ergebnisdaten der Extraktions- und Partitionierungsstufe."""

    document_dir: Path
    combined_markdown_path: Path
    extraction_json_path: Path
    task_count: int
    from_cache: bool = False


@dataclass(frozen=True)
class TaskExtractionResult(TaskProcessingResult):
    """Ergebnis der Extraktion vollständiger Aufgaben."""


@dataclass(frozen=True)
class TaskPartitioningResult(TaskProcessingResult):
    """Ergebnis der Zerlegung vollständiger Aufgaben in Unteraufgaben."""


class TaskModelPipelineBase:
    """Bündelt gemeinsame Mechanik der Extraktions- und Partitionierungsstufe."""

    operation = "Aufgabenverarbeitung"
    source_filename: str
    reviewed_source_filename: str
    source_label: str

    def __init__(
        self,
        model: BaseChatModel,
        prompt_template: str,
        document_type: str | None = None,
        progress: Callable[[str], None] | None = None,
        warn: Callable[[str], None] | None = None,
    ):
        """Initialisiert Modell, Prompt, Fortschritt und Warnungsausgabe.

        Der Prompt muss den Platzhalter ``{{ content }}`` enthalten.
        Ohne Fortschrittsfunktion werden Meldungen verworfen.

        Args:
            model: Bereits konfiguriertes LangChain-Chatmodell.
            prompt_template: Promptvorlage mit dem Platzhalter ``{{ content }}``.
            document_type: Optional festgelegter Typ des verarbeiteten Dokuments.
            progress: Optionaler Empfänger für menschenlesbare Statusmeldungen.
            warn: Separater Empfänger direkter Inhaltswarnungen, unabhängig vom Fortschritt.

        Raises:
            ValueError: Wenn der erforderliche Promptplatzhalter fehlt.
        """
        self.model = model
        self.prompt_template = create_prompt_template(
            prompt_template,
            variables=("content",),
            prompt_label="Aufgabenprompt",
        )
        self.document_type = document_type
        self.progress = progress or (lambda _message: None)
        self.warn = warn or (lambda _message: None)

    def _prepare_outputs(
        self,
        paths: list[Path],
        tasks_dir: Path,
        overwrite: bool,
    ) -> None:
        """Prüft vorhandene Ausgaben und entfernt sie bei aktiviertem Überschreiben.

        Ohne ``overwrite`` führt bereits ein vorhandenes Zielartefakt oder ein
        vorhandener Aufgabenordner zu ``FileExistsError``. Mit ``overwrite``
        werden nur die ausdrücklich übergebenen Dateien und ``tasks_dir``
        entfernt; andere Dateien bleiben erhalten.
        """
        existing = [path for path in paths if path.exists()]
        if tasks_dir.exists():
            existing.append(tasks_dir)
        if existing and not overwrite:
            raise FileExistsError(
                f"Ergebnisse der {self.operation} existieren bereits. "
                "Nutze --overwrite zum Ersetzen."
            )
        if not overwrite:
            return
        for path in paths:
            if path.is_file():
                path.unlink()
        if tasks_dir.is_dir():
            shutil.rmtree(tasks_dir)

    def _load_source_text(self, document_dir: Path) -> tuple[Path, str]:
        """Lädt bevorzugt die Reviewed-, sonst die Raw-Quelldatei als UTF-8."""
        source_path = preferred_reviewed_artifact(
            document_dir,
            raw_filename=self.source_filename,
            reviewed_filename=self.reviewed_source_filename,
        )
        if not source_path.is_file():
            raise FileNotFoundError(
                f"{self.source_label} nicht gefunden: {source_path}"
            )
        source_content = source_path.read_text(encoding="utf-8").strip()
        if not source_content:
            raise ValueError(f"{self.source_label} ist leer: {source_path}")
        return source_path, source_content

    def _write_input_artifact(
        self,
        path: Path,
        model_input: str,
    ) -> None:
        """Speichert den Modellinput als UTF-8-Artefakt."""
        path.write_text(model_input.rstrip() + "\n", encoding="utf-8")
        self.progress(f"Aufbereitete LLM-Eingabe gespeichert: {path}")
