"""Erzeugt und validiert Rubrics für strukturell ausgerichtete Blattaufgaben."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from langchain_core.prompts import PromptTemplate
from langchain_core.language_models import BaseChatModel

from grading_pipeline.infrastructure.artifact_names import RUBRIC_ARTIFACTS
from grading_pipeline.caching.common import (
    load_cached_raw_result,
    read_matching_cache,
    write_cache_document,
)
from grading_pipeline.models.metadata import model_identity
from grading_pipeline.models.responses import response_artifact, response_text
from grading_pipeline.infrastructure.json_io import write_json
from grading_pipeline.grading.documents import LoadedDocument, read_partitioned_document
from grading_pipeline.models.json import parse_model_json_object
from grading_pipeline.models.prompts import create_prompt_template
from grading_pipeline.infrastructure.pipeline_artifacts import (
    filename_stem,
    ModelCallArtifacts,
    model_call_artifacts,
    prepare_model_output,
)
from grading_pipeline.infrastructure.model_calls import invoke_json_model
from grading_pipeline.infrastructure.statistics import (
    write_model_call_statistics,
)
from .validation import validate_rubric_structure
from .reporting import render_rubrics_markdown, structure_check_payload
from .targets import (
    RubricTarget,
    build_rubric_targets,
    combine_target_and_rubric,
    target_input_payload,
)


@dataclass(frozen=True)
class RubricGenerationResult:
    """Beschreibt die erzeugten Rubric-Dateien und ihren Cache-Status."""

    output_dir: Path
    structure_check_path: Path
    rubrics_json_path: Path
    rubrics_markdown_path: Path
    rubric_count: int
    from_cache: bool
    failed_rubric_count: int = 0


@dataclass(frozen=True)
class RubricGenerationInputs:
    """Bündelt Aufgabenstellung, Musterlösung und abgeleitete Rubric-Ziele."""

    assignment: LoadedDocument
    reference_solution: LoadedDocument
    targets: list[RubricTarget]


@dataclass(frozen=True)
class RubricGenerationPaths:
    """Enthält sämtliche Datei- und Ordnerpfade eines Rubric-Laufs."""

    inputs: Path
    responses: Path
    structure: Path
    rubrics: Path
    reviewed_rubrics: Path
    cache: Path
    export: Path


@dataclass(frozen=True)
class RubricGenerationRunSetup:
    """Hält vorbereitete Pfade und Cache-Verfügbarkeit eines Rubric-Laufs."""

    output_dir: Path
    paths: RubricGenerationPaths
    cache_available: bool


@dataclass
class RubricTargetAttempt:
    """Hält den Ergebniszustand für ein Rubric-Ziel."""

    artifacts: ModelCallArtifacts
    from_cache: bool
    rubric: dict[str, Any] | None


@dataclass
class RubricGenerationState:
    """Sammelt Rubrics und Cache-Zustände eines Laufs."""

    rubrics: list[dict[str, Any]] = field(default_factory=list)
    cache_hits: list[bool] = field(default_factory=list)
    failed_count: int = 0


class RubricGenerationPipeline:
    """Erzeugt eine Rubric pro strukturell ausgerichtetem Blattknoten."""

    def __init__(
        self,
        model: BaseChatModel,
        prompt_template: str,
        progress: Callable[[str], None] | None = None,
        warn: Callable[[str], None] | None = None,
    ):
        """Konfiguriert Modell, Prompt, Warnungs- und Fortschrittsausgabe."""
        self.model = model
        self.prompt_template = create_prompt_template(
            prompt_template,
            variables=("target", "assignment", "reference_solution"),
            prompt_label="Rubric-Prompt",
        )
        self.progress = progress or (lambda _message: None)
        self.warn = warn or (lambda _message: None)

    def generate(
        self,
        *,
        assignment_dir: Path,
        reference_solution_dir: Path,
        output_dir: Path,
        overwrite: bool = False,
    ) -> RubricGenerationResult:
        """Erzeugt und speichert alle Rubrics für zwei ausgerichtete Dokumente."""
        inputs = self._load_rubric_inputs(
            assignment_dir=assignment_dir,
            reference_solution_dir=reference_solution_dir,
        )
        run = self._prepare_rubric_run(
            inputs=inputs,
            output_dir=output_dir,
            overwrite=overwrite,
        )
        state = RubricGenerationState()
        for index, target in enumerate(inputs.targets, start=1):
            attempt = self._obtain_rubric(
                inputs=inputs,
                run=run,
                target=target,
                index=index,
            )
            self._record_rubric(
                target=target,
                attempt=attempt,
                state=state,
            )
        return self._finalize_rubric_run(inputs=inputs, run=run, state=state)

    def _load_rubric_inputs(
        self,
        *,
        assignment_dir: Path,
        reference_solution_dir: Path,
    ) -> RubricGenerationInputs:
        """Lädt beide Dokumente und ermittelt ihre ausgerichteten Blattziele."""
        assignment = read_partitioned_document(
            assignment_dir,
            expected_type="assignment",
        )
        reference = read_partitioned_document(
            reference_solution_dir,
            expected_type="reference_solution",
        )
        self.progress("Pruefe parallele Aufgabenstruktur ...")
        targets = build_rubric_targets(
            assignment.data,
            reference.data,
        )
        self.progress(
            f"Strukturpruefung erfolgreich: {len(targets)} Rubric-Ziel(e)."
        )
        return RubricGenerationInputs(
            assignment=assignment,
            reference_solution=reference,
            targets=targets,
        )

    def _prepare_rubric_run(
        self,
        *,
        inputs: RubricGenerationInputs,
        output_dir: Path,
        overwrite: bool,
    ) -> RubricGenerationRunSetup:
        """Bereitet Pfade, Strukturprüfung, Cache-Identität und Cache-Einträge vor."""
        output_dir = output_dir.resolve()
        paths = self._paths(output_dir)
        cache_identity = model_identity(self.model, json_mode=True)
        cache_matches = (
            not overwrite
            and read_matching_cache(
                paths.cache,
                metadata={"model": cache_identity},
            ) is not None
        )
        self._prepare_output(
            output_dir=output_dir,
            paths=paths,
            preserve_task_cache=cache_matches,
            overwrite=overwrite,
        )
        write_json(
            paths.structure,
            structure_check_payload(
                assignment_path=inputs.assignment.path,
                reference_path=inputs.reference_solution.path,
                targets=inputs.targets,
            ),
        )
        write_cache_document(
            paths.cache,
            metadata={"model": cache_identity},
        )
        return RubricGenerationRunSetup(
            output_dir=output_dir,
            paths=paths,
            cache_available=cache_matches,
        )

    def _obtain_rubric(
        self,
        *,
        inputs: RubricGenerationInputs,
        run: RubricGenerationRunSetup,
        target: RubricTarget,
        index: int,
    ) -> RubricTargetAttempt:
        """Laedt oder erzeugt den ersten Rubric-Versuch fuer ein Blattziel."""
        model_input = render_model_input(
            self.prompt_template,
            target=target_input_payload(target),
            assignment=inputs.assignment.content,
            reference_solution=inputs.reference_solution.content,
        )
        artifacts = self._prepare_target_artifacts(
            target=target,
            index=index,
            paths=run.paths,
        )
        rubric = load_cached_raw_result(
            cache_available=run.cache_available,
            input_path=artifacts.input,
            expected_input=model_input,
            raw_path=artifacts.raw,
            label=f"Rubric für {target.path_string}",
            validator=lambda data: validate_rubric_structure(data, target),
        )
        artifacts.input.write_text(model_input.rstrip() + "\n", encoding="utf-8")
        from_cache = rubric is not None
        if rubric is None:
            if artifacts.raw.is_file():
                artifacts.raw.unlink()
            self.progress(
                f"Rubric {index}/{len(inputs.targets)} erzeugen: "
                f"{target.display_label}"
            )
            rubric = self._execute_rubric_attempt(
                prompt=model_input,
                target=target,
                index=index,
                total=len(inputs.targets),
                artifacts=artifacts,
            )
        else:
            self.progress(
                f"Rubric {index}/{len(inputs.targets)} aus Cache: "
                f"{target.display_label}"
            )
        return RubricTargetAttempt(
            artifacts=artifacts,
            from_cache=from_cache,
            rubric=rubric,
        )

    def _prepare_target_artifacts(
        self,
        *,
        target: RubricTarget,
        index: int,
        paths: RubricGenerationPaths,
    ) -> ModelCallArtifacts:
        """Bestimmt die Artefakte des Ziels."""
        stem = filename_stem(
            index,
            target.display_label,
            fallback="rubric",
        )
        return model_call_artifacts(paths.inputs, paths.responses, stem)

    def _execute_rubric_attempt(
        self,
        *,
        prompt: str,
        target: RubricTarget,
        index: int,
        total: int,
        artifacts: ModelCallArtifacts,
    ) -> dict[str, Any] | None:
        """Fuehrt einen Modellversuch aus und speichert Antwort sowie Statistik."""
        response, started_at = invoke_json_model(
            self.model,
            prompt,
            progress=self.progress,
            heartbeat_label=f"Rubric-Erstellung {index}/{total} beim Modell",
            result_label=f"Rubric {index}/{total}",
        )
        write_json(artifacts.response, response_artifact(response))
        rubric = self._assess_rubric_response(response_text(response), target)
        if rubric is not None:
            write_json(artifacts.raw, rubric)
        write_model_call_statistics(
            artifacts.statistics,
            model=self.model,
            response=response,
            stage="rubric_generation",
            model_input=prompt,
            started_at=started_at,
            warn=self.warn,
        )
        return rubric

    def _assess_rubric_response(self, content: str, target: RubricTarget) -> dict[str, Any] | None:
        """Meldet eine unbrauchbare Rubric direkt; der Lauf verarbeitet weitere Ziele."""
        try:
            data = parse_model_json_object(content, response_label="Rubric-Antwort")
            return validate_rubric_structure(data, target)
        except ValueError as error:
            self.warn(f"FEHLER: Rubric {target.path_string} wird uebersprungen: {error}")
            return None

    def _record_rubric(
        self,
        *,
        target: RubricTarget,
        attempt: RubricTargetAttempt,
        state: RubricGenerationState,
    ) -> None:
        """Übernimmt ein brauchbares Rubric und merkt seinen Cache-Status."""
        state.cache_hits.append(attempt.from_cache)
        if attempt.rubric is None:
            state.failed_count += 1
            return
        state.rubrics.append(
            combine_target_and_rubric(target, attempt.rubric)
        )

    def _finalize_rubric_run(
        self,
        *,
        inputs: RubricGenerationInputs,
        run: RubricGenerationRunSetup,
        state: RubricGenerationState,
    ) -> RubricGenerationResult:
        """Führt Einzelrubrics zusammen und schreibt JSON sowie Markdown."""
        failed_rubric_count = state.failed_count
        combined_data = {
            "status": "incomplete" if failed_rubric_count else "complete",
            "assignment_document_title": inputs.assignment.data.get(
                "document_title"
            ),
            "reference_solution_document_title": inputs.reference_solution.data.get(
                "document_title"
            ),
            "rubrics": state.rubrics,
        }
        write_json(run.paths.rubrics, combined_data)
        run.paths.export.write_text(
            render_rubrics_markdown(combined_data) + "\n",
            encoding="utf-8",
        )
        self.progress(f"Rubric-Export gespeichert: {run.paths.export}")
        return RubricGenerationResult(
            output_dir=run.output_dir,
            structure_check_path=run.paths.structure,
            rubrics_json_path=run.paths.rubrics,
            rubrics_markdown_path=run.paths.export,
            rubric_count=len(state.rubrics),
            failed_rubric_count=failed_rubric_count,
            from_cache=bool(state.cache_hits) and all(state.cache_hits),
        )

    def _paths(self, output_dir: Path) -> RubricGenerationPaths:
        """Leitet alle Ausgabepfade aus dem Wurzelordner ab."""
        return RubricGenerationPaths(
            inputs=output_dir / RUBRIC_ARTIFACTS.inputs_dir,
            responses=output_dir / RUBRIC_ARTIFACTS.responses_dir,
            structure=output_dir / RUBRIC_ARTIFACTS.structure_check,
            rubrics=output_dir / RUBRIC_ARTIFACTS.raw_json,
            reviewed_rubrics=output_dir / RUBRIC_ARTIFACTS.reviewed_json,
            cache=output_dir / RUBRIC_ARTIFACTS.cache_json,
            export=output_dir / RUBRIC_ARTIFACTS.export_markdown,
        )

    def _prepare_output(
        self,
        *,
        output_dir: Path,
        paths: RubricGenerationPaths,
        preserve_task_cache: bool,
        overwrite: bool,
    ) -> None:
        """Bereinigt veraltete Ausgaben und legt benoetigte Ordner an."""
        prepare_model_output(
            output_dir,
            working_dirs=(paths.inputs, paths.responses),
            result_files=(paths.structure, paths.rubrics, paths.export),
            cache_file=paths.cache,
            preserve_cache=preserve_task_cache,
        )
        if overwrite:
            paths.reviewed_rubrics.unlink(missing_ok=True)

def render_model_input(
    prompt_template: str | PromptTemplate,
    *,
    target: str,
    assignment: str,
    reference_solution: str,
) -> str:
    """Rendert einen Rubric-Prompt mit einer LangChain-Promptvorlage."""
    template = (
        prompt_template
        if isinstance(prompt_template, PromptTemplate)
        else create_prompt_template(
            prompt_template,
            variables=("target", "assignment", "reference_solution"),
            prompt_label="Rubric-Prompt",
        )
    )
    return template.format(
        target=target,
        assignment=assignment,
        reference_solution=reference_solution,
    )
