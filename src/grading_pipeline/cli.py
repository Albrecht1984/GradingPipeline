"""Führt die über :mod:`grading_pipeline.cli_parser` definierten CLI-Befehle aus."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Callable

from grading_pipeline.cli_parser import build_parser
from grading_pipeline.extraction import (
    TaskExtractionPipeline,
    TaskPartitioningPipeline,
    VisualExtractionPipeline,
    prepare_document_image_supplements,
    resolve_task_prompt_template,
)
from grading_pipeline.grading import GradingPipeline, MonolithicGradingPipeline
from grading_pipeline.models.factory import ChatModelConfig, create_chat_model
from grading_pipeline.rubrics import RubricGenerationPipeline
from grading_pipeline.validation import validate_artifact_directory


ProgressCallback = Callable[[str], None]


def main(argv: list[str] | None = None) -> None:
    """Parst die Kommandozeile, führt einen Unterbefehl aus und meldet Fehler."""
    parser = build_parser()
    args = parser.parse_args(argv)

    def report(message: str) -> None:
        """Gibt eine sofort sichtbare Fortschrittsmeldung mit Programmpräfix aus."""
        print(f"[GradingPipeline] {message}", flush=True)

    try:
        if args.command == "validate":
            _run_validation(args, report)
            return
        if args.command == "prepare-images":
            _run_prepare_images(args, report)
            return
        _, prompt = read_required_prompt(
            args.prompt_file,
            label="Promptdatei",
        )
        if args.command == "extract":
            _run_visual_extraction(args, prompt, report)
            return
        if args.command == "extract-tasks":
            _run_task_extraction(args, prompt, report)
            return
        if args.command == "partition-tasks":
            _run_task_partitioning(args, prompt, report)
            return
        if args.command == "create-rubrics":
            _run_rubric_generation(args, prompt, report)
            return
        if args.command in {"grade", "grade-with-images"}:
            _run_grading(args, prompt, report)
            return
        if args.command == "grade-monolithic":
            _run_monolithic_grading(args, prompt, report)
            return
        raise ValueError(f"Unbekannter Befehl: {args.command}")
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"[GradingPipeline] FEHLER: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from None


def _chat_model(args: argparse.Namespace):
    """Erzeugt das LangChain-Chatmodell einer einzelnen CLI-Stufe."""
    return create_chat_model(ChatModelConfig(
        provider=args.provider,
        model=args.model,
        ollama_base_url=args.ollama_base_url,
        ollama_num_ctx=args.ollama_num_ctx,
        openai_base_url=args.openai_base_url,
        openai_api_key_env=args.openai_api_key_env,
        timeout=args.timeout,
        temperature=args.temperature,
    ))


def _run_validation(
    args: argparse.Namespace,
    report: ProgressCallback,
) -> None:
    """Prüft einen Artefakt-Ordner ohne Modellaufruf oder Datenänderung."""
    result = validate_artifact_directory(args.input)
    for issue in result.required_issues:
        location = f" | {issue.location}" if issue.location else ""
        report(f"ERFORDERLICH: {issue.artifact}{location} | {issue.message}")
    for issue in result.quality_issues:
        location = f" | {issue.location}" if issue.location else ""
        report(f"HINWEIS: {issue.artifact}{location} | {issue.message}")
    if args.verbose and result.checked_artifacts:
        report("Geprüfte Artefakte: " + ", ".join(result.checked_artifacts))
    report(
        f"Validierung: {result.status} | "
        f"{len(result.required_issues)} erforderlich | "
        f"{len(result.quality_issues)} Qualitätshinweis(e)"
    )
    if result.required_issues:
        raise SystemExit(1)


def _run_visual_extraction(
    args: argparse.Namespace,
    prompt: str,
    report: ProgressCallback,
) -> None:
    """Konfiguriert und startet die visuelle Extraktion."""
    pipeline = VisualExtractionPipeline(
        _chat_model(args),
        prompt=prompt,
        dpi=args.dpi,
        document_type=args.document_type,
        progress=report if args.verbose else None,
    )
    result = pipeline.extract(
        source=args.input,
        output_dir=args.output_dir,
        overwrite=args.overwrite,
        use_cache=not args.overwrite,
    )
    report(f"Extrahierte Seiten: {result.page_count}")
    if args.verbose:
        report(f"Roh-Markdown: {result.markdown_path}")
        report(f"Dokument-JSON: {result.document_json_path}")


def _run_prepare_images(
    args: argparse.Namespace,
    report: ProgressCallback,
) -> None:
    """Erzeugt Bildsupplemente ohne einen Modellaufruf."""

    result = prepare_document_image_supplements(
        args.input,
        document_type=args.document_type,
    )
    report(f"Bildsupplemente: {result.image_count}")
    if args.verbose and result.manifest_path is not None:
        report(f"Manifest: {result.manifest_path}")


def _run_task_extraction(
    args: argparse.Namespace,
    prompt: str,
    report: ProgressCallback,
) -> None:
    """Konfiguriert und startet die Extraktion vollständiger Aufgaben."""
    resolved_prompt = resolve_task_prompt_template(prompt, args.document_type)
    pipeline = TaskExtractionPipeline(
        _chat_model(args),
        prompt_template=resolved_prompt,
        document_type=args.document_type,
        progress=report if args.verbose else None,
        warn=report,
    )
    result = pipeline.extract(
        document_dir=args.input,
        output_dir=args.output_dir,
        overwrite=args.overwrite,
        use_cache=not args.overwrite,
    )
    report(f"Extrahierte Aufgaben: {result.task_count}")
    if args.verbose:
        report(f"Aufgaben-Markdown: {result.combined_markdown_path}")
        report(f"Aufgaben-JSON: {result.extraction_json_path}")


def _run_task_partitioning(
    args: argparse.Namespace,
    prompt: str,
    report: ProgressCallback,
) -> None:
    """Konfiguriert und startet die Partitionierung in Unteraufgaben."""
    pipeline = TaskPartitioningPipeline(
        _chat_model(args),
        prompt_template=prompt,
        progress=report if args.verbose else None,
        warn=report,
    )
    result = pipeline.extract(
        document_dir=args.input,
        output_dir=args.output_dir,
        overwrite=args.overwrite,
        use_cache=not args.overwrite,
    )
    report(f"Partitionierte Aufgaben: {result.task_count}")
    if args.verbose:
        report(f"Partitioniertes Markdown: {result.combined_markdown_path}")
        report(f"Partitionierungs-JSON: {result.extraction_json_path}")


def _run_rubric_generation(
    args: argparse.Namespace,
    prompt: str,
    report: ProgressCallback,
) -> None:
    """Konfiguriert und startet die Rubric-Erzeugung."""
    pipeline = RubricGenerationPipeline(
        _chat_model(args),
        prompt_template=prompt,
        progress=report if args.verbose else None,
        warn=report,
    )
    result = pipeline.generate(
        assignment_dir=args.assignment_dir,
        reference_solution_dir=args.reference_solution_dir,
        output_dir=args.output_dir,
        overwrite=args.overwrite,
    )
    label = "CACHE" if result.from_cache else "NEU"
    report(f"Rubrics: {label} | {result.rubric_count} Ziel(e)")
    if args.verbose:
        report(f"Strukturprüfung: {result.structure_check_path}")
        report(f"Rubric-JSON: {result.rubrics_json_path}")
        report(f"Rubric-Markdown: {result.rubrics_markdown_path}")


def _run_grading(
    args: argparse.Namespace,
    prompt: str,
    report: ProgressCallback,
) -> None:
    """Konfiguriert und startet die Bewertung einer studentischen Lösung."""
    pipeline = GradingPipeline(
        _chat_model(args),
        prompt_template=prompt,
        with_images=args.command == "grade-with-images",
        progress=report if args.verbose else None,
        warn=report,
    )
    result = pipeline.grade(
        assignment_dir=args.assignment_dir,
        student_solution_dir=args.student_solution_dir,
        output_dir=args.output_dir,
        reference_solution_dir=args.reference_solution_dir,
        rubrics_dir=args.rubrics_dir,
        context_files=args.context,
        context_map=args.context_map,
        skip_targets=args.skip_target,
        student_id=args.student_id,
        overwrite=args.overwrite,
    )
    label = "CACHE" if result.from_cache else "NEU"
    report(f"Bewertungen: {label} | {result.graded_task_count} Blattaufgabe(n)")
    if result.failed_task_count:
        report(
            f"WARNUNG: {result.failed_task_count} Blattaufgabe(n) konnten nicht "
            "formal gültig bewertet werden."
        )
    if args.verbose:
        report(f"Strukturprüfung: {result.structure_check_path}")
        report(f"Ergebnis-JSON: {result.results_json_path}")
        report(f"Bewertungsbericht: {result.report_path}")
        report(f"Studierendenfeedback: {result.feedback_path}")


def _run_monolithic_grading(
    args: argparse.Namespace,
    prompt: str,
    report: ProgressCallback,
) -> None:
    """Konfiguriert den freien multimodalen Gesamtbewertungslauf."""

    pipeline = MonolithicGradingPipeline(
        _chat_model(args),
        prompt=prompt,
        dpi=args.dpi,
        progress=report if args.verbose else None,
    )
    result = pipeline.grade(
        input_dir=args.input,
        output_dir=args.output_dir,
        overwrite=args.overwrite,
    )
    label = "CACHE" if result.from_cache else "NEU"
    report(f"Monolithische Bewertung: {label} | {result.page_count} Seite(n)")
    if args.verbose:
        report(f"Freie Modellantwort: {result.raw_text_path}")
        report(f"Providerantwort: {result.response_path}")


def read_required_prompt(
    supplied_path: Path,
    *,
    label: str,
) -> tuple[Path, str]:
    """Liest einen nicht leeren UTF-8-Prompt und liefert seinen absoluten Pfad."""
    path = supplied_path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label} nicht gefunden: {path}")
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} ist nicht UTF-8-kodiert: {path}") from exc
    if not content.strip():
        raise ValueError(f"{label} ist leer: {path}")
    return path, content
