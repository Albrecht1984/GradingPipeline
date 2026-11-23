"""Bewertet strukturell ausgerichtete studentische Lösungen auf Blattebene."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from grading_pipeline.infrastructure.artifact_names import GRADING_ARTIFACTS
from grading_pipeline.caching.common import (
    load_cached_raw_result,
    read_matching_cache,
    write_cache_document,
)
from .reporting import write_reports
from .schema import FailedTaskGrading, GradingDocumentResult, TaskGrading
from .documents import (
    LoadedDocument,
    read_partitioned_document,
    read_rubrics,
)
from .context import LoadedTaskContextMap, read_task_context_map
from .input import build_grader_input
from .images import (
    GradingImageGroup,
    collect_grading_image_groups,
    stored_image_groups_match,
)
from .structure import GradingUnit, build_grading_units
from .structure_report import structure_check_payload
from grading_pipeline.models.metadata import model_identity
from grading_pipeline.models.responses import response_artifact, response_text
from langchain_core.language_models import BaseChatModel
from grading_pipeline.models.json import parse_model_json_object
from grading_pipeline.models.prompts import create_prompt_template
from grading_pipeline.infrastructure.json_io import (
    write_json,
)
from grading_pipeline.infrastructure.pipeline_artifacts import (
    ContextMaterial,
    read_context_material,
    filename_stem,
    ModelCallArtifacts,
    model_call_artifacts,
    prepare_model_output,
)
from grading_pipeline.infrastructure.model_calls import (
    MultimodalImage,
    MultimodalImageGroup,
    invoke_json_model,
    invoke_multimodal_json_model,
)
from grading_pipeline.infrastructure.statistics import (
    write_model_call_statistics,
)
from .validation import parse_grading_response


@dataclass(frozen=True)
class GradingPipelineResult:
    """Beschreibt Ergebnisdateien, Aufgabenzahlen und Cache-Status eines Laufs."""

    output_dir: Path
    structure_check_path: Path
    results_json_path: Path
    report_path: Path
    feedback_path: Path
    graded_task_count: int
    failed_task_count: int
    from_cache: bool


@dataclass(frozen=True)
class GradingInputs:
    """Bündelt geladene Dokumente und daraus abgeleitete Bewertungsinputs."""

    assignment: LoadedDocument
    student_solution: LoadedDocument
    reference_solution: LoadedDocument | None
    rubrics: LoadedDocument | None
    context_material: list[ContextMaterial]
    task_context_map: LoadedTaskContextMap | None
    units: list[GradingUnit]


@dataclass(frozen=True)
class GradingPaths:
    """Enthält sämtliche Datei- und Ordnerpfade eines Bewertungslaufs."""

    root: Path
    structure: Path
    inputs: Path
    responses: Path
    results: Path
    cache: Path
    report: Path
    feedback: Path


@dataclass(frozen=True)
class GradingRunSetup:
    """Hält vorbereitete Pfade und Cache-Verfügbarkeit."""

    paths: GradingPaths
    cache_available: bool


@dataclass
class GradingRunState:
    """Sammelt Ergebnisse, Fehlschläge und Artefaktmetadaten eines Laufs."""

    task_results: list[TaskGrading] = field(default_factory=list)
    failed_tasks: list[FailedTaskGrading] = field(default_factory=list)
    cache_hits: list[bool] = field(default_factory=list)


class GradingPipeline:
    """Bewertet strukturell ausgerichtete Blattaufgaben mit je einem Modellaufruf."""

    def __init__(
            self,
            model: BaseChatModel,
            prompt_template: str,
            with_images: bool = False,
            progress: Callable[[str], None] | None = None,
            warn: Callable[[str], None] | None = None,
    ):
        """Konfiguriert die Bewertungspipeline und ihre Modellabhängigkeiten."""
        self.model = model
        self.with_images = with_images
        self.prompt_template = create_prompt_template(
            prompt_template,
            variables=("grading_input",),
            prompt_label="Bewertungsprompt",
        )
        self.progress = progress or (lambda _message: None)
        self.warn = warn or (lambda _message: None)

    def grade(
            self,
            *,
            assignment_dir: Path,
            student_solution_dir: Path,
            output_dir: Path,
            reference_solution_dir: Path | None = None,
            rubrics_dir: Path | None = None,
            context_files: list[Path] | None = None,
            context_map: Path | None = None,
            skip_targets: list[str] | None = None,
            student_id: str | None = None,
            overwrite: bool = False,
    ) -> GradingPipelineResult:
        """Bewertet alle Blattaufgaben und erzeugt Cache, Ergebnisse und Berichte."""
        inputs = self._load_grading_inputs(
            assignment_dir=assignment_dir,
            student_solution_dir=student_solution_dir,
            reference_solution_dir=reference_solution_dir,
            rubrics_dir=rubrics_dir,
            context_files=context_files or [],
            context_map=context_map,
        )
        units = inputs.units
        targets_to_skip = self._validated_skip_targets(skip_targets or [], units)
        run = self._prepare_grading_run(
            inputs=inputs,
            output_dir=output_dir,
            overwrite=overwrite,
        )
        paths = run.paths
        output_dir = paths.root
        state = GradingRunState()

        for index, unit in enumerate(units, start=1):
            if unit.path_string in targets_to_skip:
                self.progress(
                    f"Bewertung {index}/{len(units)} übersprungen "
                    f"(runtime_failure): {unit.display_label}"
                )
                self._record_failed_unit(
                    unit=unit,
                    state=state,
                    failure_tag="runtime_failure",
                )
                continue
            result, from_cache = self._grade_unit(
                unit=unit,
                index=index,
                total=len(units),
                paths=paths,
                cache_available=run.cache_available,
                context_material=self._context_for_unit(unit, inputs),
                inputs=inputs,
            )
            if result is None:
                self._record_failed_unit(
                    unit=unit,
                    state=state,
                )
            else:
                self._record_successful_unit(
                    result=result,
                    from_cache=from_cache,
                    state=state,
                )

        return self._finalize_grading_run(
            output_dir=output_dir,
            paths=paths,
            student_id=student_id,
            task_results=state.task_results,
            failed_tasks=state.failed_tasks,
            cache_hits=state.cache_hits,
        )

    def _paths(self, output_dir: Path) -> GradingPaths:
        """Leitet alle von der Pipeline verwendeten Pfade vom Ausgabeordner ab."""
        return GradingPaths(
            root=output_dir,
            structure=output_dir / GRADING_ARTIFACTS.structure_check,
            inputs=output_dir / GRADING_ARTIFACTS.inputs_dir,
            responses=output_dir / GRADING_ARTIFACTS.responses_dir,
            results=output_dir / GRADING_ARTIFACTS.results_json,
            cache=output_dir / GRADING_ARTIFACTS.cache_json,
            report=output_dir / GRADING_ARTIFACTS.report_markdown,
            feedback=output_dir / GRADING_ARTIFACTS.feedback_markdown,
        )

    def _load_grading_inputs(
            self,
            *,
            assignment_dir: Path,
            student_solution_dir: Path,
            reference_solution_dir: Path | None,
            rubrics_dir: Path | None,
            context_files: list[Path],
            context_map: Path | None,
    ) -> GradingInputs:
        """Lädt die Dokumente und baut daraus die zu bewertenden Blattaufgaben."""
        assignment = read_partitioned_document(
            assignment_dir, expected_type="assignment"
        )
        student_solution = read_partitioned_document(
            student_solution_dir, expected_type="student_solution"
        )
        reference_solution = (
            read_partitioned_document(
                reference_solution_dir, expected_type="reference_solution"
            )
            if reference_solution_dir is not None
            else None
        )
        rubrics = read_rubrics(rubrics_dir) if rubrics_dir is not None else None
        context_material = read_context_material(context_files)
        self.progress("Pruefe die rekursive Dokumentstruktur ...")
        units = build_grading_units(
            assignment.data,
            student_solution.data,
            reference_solution=(
                reference_solution.data if reference_solution is not None else None
            ),
            rubrics=rubrics.data if rubrics is not None else None,
        )
        task_context_map = (
            read_task_context_map(
                context_map,
                expected_target_paths=[unit.path_string for unit in units],
            )
            if context_map is not None
            else None
        )
        self.progress(f"Strukturpruefung erfolgreich: {len(units)} Blattaufgabe(n).")
        return GradingInputs(
            assignment=assignment,
            student_solution=student_solution,
            reference_solution=reference_solution,
            rubrics=rubrics,
            context_material=context_material,
            task_context_map=task_context_map,
            units=units,
        )

    @staticmethod
    def _validated_skip_targets(
        skip_targets: list[str],
        units: list[GradingUnit],
    ) -> set[str]:
        """Prüft explizit übersprungene Blattknoten gegen die Aufgabenstruktur."""

        requested = set(skip_targets)
        available = {unit.path_string for unit in units}
        unknown = sorted(requested - available)
        if unknown:
            raise ValueError(
                "Unbekannte --skip-target-Angabe(n): " + ", ".join(unknown)
            )
        return requested

    def _prepare_grading_run(
        self,
        *,
        inputs: GradingInputs,
        output_dir: Path,
        overwrite: bool,
    ) -> GradingRunSetup:
        """Bereitet Ausgabeordner, Strukturprüfung und wiederverwendbaren Cache vor."""
        output_dir = output_dir.resolve()
        paths = self._paths(output_dir)
        cache_identity = model_identity(self.model, json_mode=True)
        grading_mode = "vision" if self.with_images else "text"
        preserve_cache = (
            not overwrite
            and read_matching_cache(
                paths.cache,
                metadata={"model": cache_identity, "grading_mode": grading_mode},
            ) is not None
        )
        self._prepare_output(paths, preserve_cache=preserve_cache)
        write_cache_document(
            paths.cache,
            metadata={"model": cache_identity, "grading_mode": grading_mode},
        )
        structure_data = structure_check_payload(
            assignment=inputs.assignment,
            student_solution=inputs.student_solution,
            reference_solution=inputs.reference_solution,
            rubrics=inputs.rubrics,
            units=inputs.units,
            task_context_map=inputs.task_context_map,
        )
        structure_data["context_material"] = [
            {"path": item.path.name} for item in inputs.context_material
        ]
        structure_data["grading_mode"] = grading_mode
        write_json(paths.structure, structure_data)
        return GradingRunSetup(
            paths=paths,
            cache_available=preserve_cache,
        )

    @staticmethod
    def _context_for_unit(
        unit: GradingUnit,
        inputs: GradingInputs,
    ) -> list[ContextMaterial]:
        """Kombiniert globalen und explizit zugeordneten Kontext einer Blattaufgabe."""

        task_context = (
            inputs.task_context_map.by_target_path[unit.path_string]
            if inputs.task_context_map is not None
            else []
        )
        return [*inputs.context_material, *task_context]

    def _finalize_grading_run(
            self,
            *,
            output_dir: Path,
            paths: GradingPaths,
            student_id: str | None,
            task_results: list[TaskGrading],
            failed_tasks: list[FailedTaskGrading],
            cache_hits: list[bool],
    ) -> GradingPipelineResult:
        """Schreibt die zusammengeführten Endergebnisse und Abschlussberichte."""
        document_result = combine_results(student_id, task_results, failed_tasks)
        write_json(paths.results, document_result.to_dict())
        report_path, feedback_path = write_reports(document_result, output_dir)
        self.progress(f"Bewertungsbericht gespeichert: {report_path}")
        return GradingPipelineResult(
            output_dir=output_dir,
            structure_check_path=paths.structure,
            results_json_path=paths.results,
            report_path=report_path,
            feedback_path=feedback_path,
            graded_task_count=len(task_results),
            failed_task_count=len(failed_tasks),
            from_cache=bool(cache_hits)
                       and not failed_tasks
                       and all(cache_hits),
        )

    def _grade_unit(
            self,
            *,
            unit: GradingUnit,
            index: int,
            total: int,
            paths: GradingPaths,
            cache_available: bool,
            context_material: list[ContextMaterial],
            inputs: GradingInputs,
    ) -> tuple[TaskGrading | None, bool]:
        """Lädt eine Bewertung aus dem Cache oder ruft einmal das Modell auf."""
        prompt = self._build_prompt(unit, context_material)
        image_groups = (
            self._image_groups_for_unit(unit, inputs) if self.with_images else []
        )
        stored_input = grading_input_artifact(prompt, image_groups)
        artifacts = self._prepare_unit_artifacts(
            unit=unit,
            index=index,
            paths=paths,
        )
        image_identity_path = _image_identity_path(artifacts.input)
        image_identity = grading_image_identity(image_groups)
        image_identity_matches = (
            not self.with_images
            or stored_image_groups_match(image_identity_path, image_identity)
        )

        result = load_cached_raw_result(
            cache_available=cache_available and image_identity_matches,
            input_path=artifacts.input,
            expected_input=stored_input,
            raw_path=artifacts.raw,
            label=f"Bewertung für {unit.path_string}",
            validator=lambda data: parse_grading_response(
                data,
                target_path=unit.path_string,
                display_label=unit.display_label,
                expected_max_points=unit.max_points,
            ),
        )
        artifacts.input.write_text(stored_input.rstrip() + "\n", encoding="utf-8")
        if self.with_images:
            write_json(image_identity_path, image_identity)
        from_cache = result is not None
        if result is None:
            if artifacts.raw.is_file():
                artifacts.raw.unlink()
            self.progress(f"Bewertung {index}/{total}: {unit.display_label}")
            result = self._invoke_model(
                prompt=prompt, image_groups=image_groups, unit=unit,
                index=index, total=total,
                artifacts=artifacts,
            )
        else:
            self.progress(f"Bewertung {index}/{total} aus Cache: {unit.display_label}")
        return result, from_cache

    def _prepare_unit_artifacts(
            self,
            *,
            unit: GradingUnit,
            index: int,
            paths: GradingPaths,
    ) -> ModelCallArtifacts:
        """Bestimmt die Artefaktpfade einer Aufgabe."""
        stem = filename_stem(index, unit.display_label, fallback="task")
        return model_call_artifacts(paths.inputs, paths.responses, stem)

    @staticmethod
    def _record_failed_unit(
            *,
            unit: GradingUnit,
            state: GradingRunState,
            failure_tag: str | None = None,
    ) -> None:
        """Nimmt eine endgültig ungültige Bewertung in das Ergebnis auf."""
        state.failed_tasks.append(
            FailedTaskGrading(
                target_path=unit.path_string,
                display_label=unit.display_label,
                failure_tag=failure_tag,
            )
        )
        state.cache_hits.append(False)

    @staticmethod
    def _record_successful_unit(
            *,
            result: TaskGrading,
            from_cache: bool,
            state: GradingRunState,
    ) -> None:
        """Ergänzt die Ergebnisliste um eine gültige Bewertung."""
        state.task_results.append(result)
        state.cache_hits.append(from_cache)

    def _invoke_model(
            self,
            *,
            prompt: str,
            image_groups: list[GradingImageGroup],
            unit: GradingUnit,
            index: int,
            total: int,
            artifacts: ModelCallArtifacts,
    ) -> TaskGrading | None:
        """Ruft das Modell auf und speichert Antwort, Ergebnis und Statistik."""
        if self.with_images:
            response, started_at = invoke_multimodal_json_model(
                self.model,
                prompt,
                [
                    MultimodalImageGroup(
                        label=group.label,
                        images=tuple(
                            MultimodalImage(
                                image_id=image.image_id,
                                path=image.path,
                            )
                            for image in group.images
                        ),
                    )
                    for group in image_groups
                ],
                progress=self.progress,
                heartbeat_label=f"Vision-Bewertung {index}/{total} beim Modell",
                result_label=f"Vision-Bewertung {index}/{total}",
            )
        else:
            response, started_at = invoke_json_model(
                self.model,
                prompt,
                progress=self.progress,
                heartbeat_label=f"Bewertung {index}/{total} beim Modell",
                result_label=f"Bewertung {index}/{total}",
            )
        write_json(artifacts.response, response_artifact(response))
        result = self._assess_response(response_text(response), unit)
        if result is not None:
            write_json(artifacts.raw, model_result_payload(result))
        write_model_call_statistics(
            artifacts.statistics,
            model=self.model,
            response=response,
            stage="grading_with_images" if self.with_images else "grading",
            model_input=prompt,
            started_at=started_at,
            complexity={"image_count": _image_count(image_groups)}
            if self.with_images else None,
            warn=self.warn,
        )
        return result

    def _prepare_output(
            self,
            paths: GradingPaths,
            *,
            preserve_cache: bool,
    ) -> None:
        """Bereinigt veraltete Ausgaben und legt die benötigten Unterordner an."""
        root = paths.root
        prepare_model_output(
            root,
            working_dirs=(paths.inputs, paths.responses),
            result_files=(paths.structure, paths.results, paths.report, paths.feedback),
            cache_file=paths.cache,
            preserve_cache=preserve_cache,
        )

    def _build_prompt(
            self,
            unit: GradingUnit,
            context_material: list[ContextMaterial],
    ) -> str:
        """Setzt die aufgabenspezifischen Bewertungsdaten in den Prompt ein."""
        grader_input = build_grader_input(
            unit,
            context_material=context_material,
        )
        return self.prompt_template.format(grading_input=grader_input)

    def _image_groups_for_unit(
        self,
        unit: GradingUnit,
        inputs: GradingInputs,
    ) -> list[GradingImageGroup]:
        """Löst Bildreferenzen als fest geordnete Quellgruppen auf."""

        return collect_grading_image_groups(
            assignment=inputs.assignment.data,
            assignment_dir=inputs.assignment.path.parent,
            student_solution=inputs.student_solution.data,
            student_solution_dir=inputs.student_solution.path.parent,
            reference_solution=(
                inputs.reference_solution.data
                if inputs.reference_solution is not None
                else None
            ),
            reference_solution_dir=(
                inputs.reference_solution.path.parent
                if inputs.reference_solution is not None
                else None
            ),
            task_path=unit.path,
        )

    def _assess_response(self, content: str, unit: GradingUnit) -> TaskGrading | None:
        """Gibt Warnungen direkt aus; eine unbrauchbare Einzelbewertung wird übersprungen."""
        try:
            return parse_grading_response(
                parse_model_json_object(
                    content,
                    response_label="Bewertungsantwort",
                ),
                target_path=unit.path_string,
                display_label=unit.display_label, expected_max_points=unit.max_points,
            )
        except ValueError as error:
            self.warn(f"FEHLER: Bewertung {unit.path_string} wird uebersprungen: {error}")
            return None

def model_result_payload(result: TaskGrading) -> dict[str, Any]:
    """Reduziert ein validiertes Ergebnis auf die vom Modell gelieferten Felder."""
    data = result.to_dict()
    data.pop("target_path")
    data.pop("display_label")
    return data


def grading_input_artifact(
    prompt: str,
    image_groups: list[GradingImageGroup],
) -> str:
    """Spiegelt den gruppierten Request ohne Binärdaten oder Prüfsummen wider."""

    if not image_groups:
        return prompt
    parts = [prompt.rstrip()]
    for group in image_groups:
        parts.append(f'<BILDGRUPPE quelle="{group.label}">')
        parts.extend(
            f'<BILD id="{image.image_id}" />'
            for image in group.images
        )
        parts.append("</BILDGRUPPE>")
    return "\n\n".join(parts)


def grading_image_identity(
    image_groups: list[GradingImageGroup],
) -> dict[str, object]:
    """Erzeugt die nicht an das Modell gesendete Cache-Identität der Bilder."""

    return {
        "groups": [
            {
                "source_role": group.source_role,
                "images": [
                    {
                        "id": image.image_id,
                        "path": image.path.name,
                        "sha256": image.sha256,
                    }
                    for image in group.images
                ],
            }
            for group in image_groups
        ],
    }


def _image_identity_path(input_path: Path) -> Path:
    """Leitet das interne Cache-Artefakt vom sichtbaren Inputartefakt ab."""

    suffix = ".input.md"
    if not input_path.name.endswith(suffix):
        raise ValueError(f"Unerwarteter Pfad des Grading-Inputs: {input_path}")
    stem = input_path.name[:-len(suffix)]
    return input_path.with_name(f"{stem}.images.json")


def _image_count(image_groups: list[GradingImageGroup]) -> int:
    """Zählt Bilder über alle Quellgruppen hinweg."""

    return sum(len(group.images) for group in image_groups)


def combine_results(
        student_id: str | None,
        task_results: list[TaskGrading],
        failed_tasks: list[FailedTaskGrading] | None = None,
) -> GradingDocumentResult:
    """Fasst Einzelbewertungen zusammen und berechnet bei Vollständigkeit Summen."""
    failures = failed_tasks or []
    all_scored = all(
        result.points is not None and result.max_points is not None
        for result in task_results
    )
    complete_and_scored = not failures and all_scored
    points = (
        sum(result.points or 0.0 for result in task_results)
        if complete_and_scored
        else None
    )
    max_points = (
        sum(result.max_points or 0.0 for result in task_results)
        if complete_and_scored
        else None
    )
    return GradingDocumentResult(
        student_id=student_id.strip() if student_id and student_id.strip() else None,
        points=points,
        max_points=max_points,
        task_results=tuple(task_results),
        failed_tasks=tuple(failures),
    )
