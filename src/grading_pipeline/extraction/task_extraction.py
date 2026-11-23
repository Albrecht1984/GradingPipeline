"""Extrahiert vollständige Aufgaben aus dem Markdown eines vorbereiteten Dokuments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Any, Callable

from grading_pipeline.infrastructure.artifact_names import (
    TASK_EXTRACTION_ARTIFACTS,
    VISUAL_EXTRACTION_ARTIFACTS,
)
from grading_pipeline.infrastructure.model_calls import invoke_json_model
from grading_pipeline.models.metadata import model_identity, model_label
from grading_pipeline.models.responses import response_artifact, response_text
from grading_pipeline.models.json import parse_model_json_object
from grading_pipeline.models.prompts import render_prompt_template
from grading_pipeline.infrastructure.json_io import write_json
from grading_pipeline.infrastructure.task_nodes import node_label, node_text
from grading_pipeline.caching.common import (
    load_cached_raw_result,
    read_matching_cache,
    write_cache_document,
)
from grading_pipeline.infrastructure.statistics import (
    write_model_call_statistics,
)
from .artifacts import (
    render_heading,
    write_task_markdown_artifacts,
)
from .base import TaskExtractionResult, TaskModelPipelineBase
from .image_supplements import load_prepared_image_supplements
from grading_pipeline.validation import DOCUMENT_TYPES, validate_tasks

DOCUMENT_PROMPT_VALUES = {
    "assignment": {
        "document_description": "einer Aufgabensammlung",
        "editing_prohibition": "Loese oder beantworte keine Aufgabe.",
        "points_policy": (
            "Uebernimm die sichtbar fuer die gesamte Aufgabe angegebene "
            "Gesamtpunktzahl als Zahl in `points`. Ist keine Gesamtpunktzahl "
            "sichtbar, setze `points` auf `null`. Berechne oder summiere keine "
            "Punktzahl. Entferne die in `points` gespeicherte Gesamtpunktzahl "
            "aus `markdown`; Punkteangaben einzelner Unteraufgaben bleiben erhalten."
        ),
        "points_example": "15",
    },
    "reference_solution": {
        "document_description": "einer Sammlung von Musterloesungen",
        "editing_prohibition": (
            "Vervollstaendige, verbessere oder bewerte keine Musterloesung."
        ),
        "points_policy": (
            "Setze `points` auf `null`. Punkteangaben innerhalb der Loesung "
            "bleiben unveraendert in `markdown` erhalten."
        ),
        "points_example": "null",
    },
    "student_solution": {
        "document_description": "einer Sammlung studentischer Loesungen",
        "editing_prohibition": (
            "Vervollstaendige, verbessere oder bewerte keine studentische Loesung."
        ),
        "points_policy": (
            "Setze `points` auf `null`. Punkteangaben innerhalb der Loesung "
            "bleiben unveraendert in `markdown` erhalten."
        ),
        "points_example": "null",
    },
}


@dataclass(frozen=True)
class TaskExtractionPaths:
    """Enthält sämtliche Artefaktpfade der Aufgabenextraktion."""

    input: Path
    raw: Path
    reviewed: Path
    response: Path
    cache: Path
    statistics: Path
    tasks: Path
    combined: Path


@dataclass(frozen=True)
class TaskExtractionRunSetup:
    """Hält Quellen, Prompt, Cache und Pfade eines vorbereiteten Laufs."""

    document_dir: Path
    prompt: str
    cache_metadata: dict[str, Any]
    paths: TaskExtractionPaths


def resolve_task_prompt_template(prompt_template: str, document_type: str) -> str:
    """Setzt die dokumenttypspezifischen Regeln in den Extraktionsprompt ein."""
    if document_type not in DOCUMENT_TYPES:
        raise ValueError(f"Unbekannter Dokumenttyp: {document_type}")
    values = {
        "document_type": document_type,
        **DOCUMENT_PROMPT_VALUES[document_type],
    }
    return render_prompt_template(
        prompt_template,
        values={**values, "content": "{{ content }}"},
        prompt_label="Aufgabenprompt",
    )


class TaskExtractionPipeline(TaskModelPipelineBase):
    """Extrahiert vollständige Aufgaben in einem semantischen Modelldurchlauf."""

    source_filename = TASK_EXTRACTION_ARTIFACTS.source
    reviewed_source_filename = VISUAL_EXTRACTION_ARTIFACTS.reviewed_markdown
    source_label = "Rohmarkdown der Visual Extraction"
    tasks_dirname = TASK_EXTRACTION_ARTIFACTS.tasks_dir
    export_filename = TASK_EXTRACTION_ARTIFACTS.export_markdown
    operation = "Aufgabenextraktion"

    def extract(
        self,
        document_dir: Path,
        *,
        output_dir: Path | None = None,
        overwrite: bool = False,
        use_cache: bool = False,
    ) -> TaskExtractionResult:
        """Extrahiert Aufgaben und schreibt Ergebnisse optional in einen separaten Ordner.

        Ohne ``output_dir`` bleibt das bisherige Verhalten erhalten: Eingabe- und
        Ausgabeordner sind identisch. Bei einem separaten Ausgabeordner werden die
        Visual-Extraction-Artefakte ausschließlich aus ``document_dir`` gelesen.
        """
        prepared = self._prepare_task_extraction_run(
            document_dir=document_dir,
            output_dir=output_dir,
            overwrite=overwrite,
            use_cache=use_cache,
        )
        if isinstance(prepared, TaskExtractionResult):
            return prepared
        run = prepared
        data = self._extract_tasks(run)
        return self._finalize_task_extraction(run=run, data=data)

    def _prepare_task_extraction_run(
        self,
        *,
        document_dir: Path,
        output_dir: Path | None,
        overwrite: bool,
        use_cache: bool,
    ) -> TaskExtractionRunSetup | TaskExtractionResult:
        """Bereitet Quelle, Cache-Zustand, Artefakte und Prompt eines Laufs vor."""
        document_dir = document_dir.resolve()
        source_path, source_content = self._load_source_text(document_dir)
        supplements = load_prepared_image_supplements(
            document_dir,
            source_content,
            source_markdown_path=source_path,
            document_type=self.document_type,
        )
        source_content = supplements.markdown
        if supplements.manifest_path is not None:
            self.progress(
                f"Bildsupplemente geladen: {supplements.image_count} Bild(er) | "
                f"{supplements.manifest_path}"
            )
        prompt = self.prompt_template.format(content=source_content)
        cache_metadata = {"model": model_identity(self.model, json_mode=True)}
        resolved_output_dir = (
            output_dir.resolve() if output_dir is not None else document_dir
        )
        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        paths = self._paths(resolved_output_dir)
        cache_available = (
            use_cache
            and not overwrite
            and read_matching_cache(
                paths.cache,
                metadata=cache_metadata,
            ) is not None
        )
        cached_result = self._load_cached_extraction(
            document_dir=resolved_output_dir,
            expected_input=prompt,
            cache_available=cache_available,
            paths=paths,
        )
        if cached_result is not None:
            return cached_result
        self._prepare_run_outputs(
            paths=paths,
            overwrite=overwrite,
            use_cache=use_cache,
        )
        paths.input.write_text(prompt.rstrip() + "\n", encoding="utf-8")
        self.progress(f"Quelle: {source_path}")
        self.progress(f"Ausgabe: {resolved_output_dir}")
        model_name, base_url = model_label(self.model)
        self.progress(f"Modell: {model_name} ({base_url or 'Standardendpunkt'})")
        return TaskExtractionRunSetup(
            document_dir=resolved_output_dir,
            prompt=prompt,
            cache_metadata=cache_metadata,
            paths=paths,
        )

    def _paths(self, document_dir: Path) -> TaskExtractionPaths:
        """Leitet alle kanonischen Extraktionspfade aus dem Dokumentordner ab."""
        return TaskExtractionPaths(
            input=document_dir / TASK_EXTRACTION_ARTIFACTS.input_markdown,
            raw=document_dir / TASK_EXTRACTION_ARTIFACTS.raw_json,
            reviewed=document_dir / TASK_EXTRACTION_ARTIFACTS.reviewed_json,
            response=document_dir / TASK_EXTRACTION_ARTIFACTS.response_json,
            cache=document_dir / TASK_EXTRACTION_ARTIFACTS.cache_json,
            statistics=document_dir / TASK_EXTRACTION_ARTIFACTS.statistics_json,
            tasks=document_dir / self.tasks_dirname,
            combined=document_dir / self.export_filename,
        )

    def _load_cached_extraction(
        self,
        *,
        document_dir: Path,
        expected_input: str,
        cache_available: bool,
        paths: TaskExtractionPaths,
    ) -> TaskExtractionResult | None:
        """Lädt einen gültigen Cache-Treffer und meldet dessen Inhaltswarnungen."""
        if not cache_available:
            return None
        self.progress("Pruefe Aufgaben-Cache ...")
        cached_data = load_cached_raw_result(
            cache_available=True,
            input_path=paths.input,
            expected_input=expected_input,
            raw_path=paths.raw,
            label="Aufgabenextraktion",
            validator=self._validate,
        )
        if cached_data is None:
            self.progress("Kein passender Modell-Cache: Segmentierung wird neu erstellt.")
            return None
        if paths.tasks.is_dir():
            shutil.rmtree(paths.tasks)
        tasks = cached_data["tasks"]
        self._write_task_artifacts(
            paths=paths,
            data=cached_data,
            tasks=tasks,
            write_raw=False,
        )
        self.progress(
            f"Modell-Cache-Treffer: {len(tasks)} Aufgabe(n) werden nicht "
            "erneut segmentiert."
        )
        return TaskExtractionResult(
            document_dir=document_dir,
            combined_markdown_path=paths.combined,
            extraction_json_path=paths.raw,
            task_count=len(tasks),
            from_cache=True,
        )

    def _prepare_run_outputs(
        self,
        *,
        paths: TaskExtractionPaths,
        overwrite: bool,
        use_cache: bool,
    ) -> None:
        """Bereitet die regulären Ausgabedateien eines neuen Laufs vor."""
        output_paths = [
            paths.input,
            paths.raw,
            paths.response,
            paths.cache,
            paths.statistics,
            paths.combined,
        ]
        self._prepare_outputs(
            paths=output_paths,
            tasks_dir=paths.tasks,
            overwrite=overwrite or use_cache,
        )
        if overwrite:
            paths.reviewed.unlink(missing_ok=True)

    def _extract_tasks(self, run: TaskExtractionRunSetup) -> dict[str, Any]:
        """Speichert die einzige Modellantwort und prüft sie ohne Reparaturversuch."""
        self.progress(f"Sende die Eingabe zur semantischen {self.operation} an das Modell ...")
        response, started_at = invoke_json_model(
            self.model,
            run.prompt,
            progress=self.progress,
            heartbeat_label=f"{self.operation} beim Modell",
            result_label="Modell",
        )
        write_json(run.paths.response, response_artifact(response))
        write_model_call_statistics(
            run.paths.statistics,
            model=self.model,
            response=response,
            stage="task_extraction",
            model_input=run.prompt,
            started_at=started_at,
            warn=self.warn,
        )
        data = parse_model_json_object(
            response_text(response),
            response_label="Modellantwort",
        )
        self._validate(data)
        return data

    def _finalize_task_extraction(
        self,
        *,
        run: TaskExtractionRunSetup,
        data: dict[str, Any],
    ) -> TaskExtractionResult:
        """Schreibt Aufgabenexport und Cache nach erfolgreicher Formatprüfung."""
        tasks = data["tasks"]
        self.progress(
            f"Das Modell hat {len(tasks)} Aufgabe(n) verarbeitet."
        )
        self._write_task_artifacts(paths=run.paths, data=data, tasks=tasks)
        write_cache_document(
            run.paths.cache,
            metadata=run.cache_metadata,
        )
        self.progress(f"Aufgabenexport gespeichert: {run.paths.combined}")
        self.progress(f"{self.operation} abgeschlossen.")
        return TaskExtractionResult(
            document_dir=run.document_dir,
            combined_markdown_path=run.paths.combined,
            extraction_json_path=run.paths.raw,
            task_count=len(tasks),
        )

    def _write_task_artifacts(
        self,
        *,
        paths: TaskExtractionPaths,
        data: dict[str, Any],
        tasks: list[dict[str, Any]],
        write_raw: bool = True,
    ) -> None:
        """Schreibt bei Bedarf Raw-JSON und baut sämtliche Textausgaben neu."""
        if write_raw:
            write_json(paths.raw, data)
        write_task_markdown_artifacts(
            tasks,
            tasks_dir=paths.tasks,
            export_path=paths.combined,
            render=render_extracted_task,
            progress=self.progress,
        )
    def _validate(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validiert und liefert eine geparste Aufgabenextraktion zurück."""
        validate_tasks(data, expected_document_type=self.document_type)
        return data

def render_extracted_task(task: dict[str, Any]) -> str:
    """Erzeugt Überschrift und bereinigten Markdown-Inhalt einer Aufgabe."""
    task_id = node_label(task, "Aufgabe")
    body = node_text(task, "markdown").strip()
    heading = render_heading(task_id, task.get("title"), task.get("points"), level=2)
    return "\n\n".join(part for part in (heading, body) if part).strip()
