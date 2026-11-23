"""Definiert die Argumente der ``grading_pipeline``-Kommandozeile."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from grading_pipeline.extraction.task_extraction import DOCUMENT_TYPES


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_VISUAL_EXTRACTION_PROMPT_PATH = ROOT / "prompts" / "extract_page.txt"
DEFAULT_TASK_EXTRACTION_PROMPT_PATH = ROOT / "prompts" / "extract_tasks.txt"
DEFAULT_TASK_PARTITIONING_PROMPT_PATH = ROOT / "prompts" / "extract_tasks_partitioned.txt"
DEFAULT_RUBRIC_PROMPT_PATH = ROOT / "prompts" / "create_rubric.txt"
DEFAULT_GRADING_PROMPT_PATH = ROOT / "prompts" / "grade_task.txt"
DEFAULT_IMAGE_GRADING_PROMPT_PATH = ROOT / "prompts" / "grade_task_with_images.txt"
DEFAULT_MONOLITHIC_GRADING_PROMPT_PATH = ROOT / "prompts" / "grade_monolithic.txt"
MODEL_PROVIDERS = ("ollama", "openai")


def boolean_value(value: str) -> bool:
    """Akzeptiert ausschließlich die expliziten Werte true und false."""
    if value == "true":
        return True
    if value == "false":
        return False
    raise argparse.ArgumentTypeError("Erwartet wird true oder false.")


def positive_int(value: str) -> int:
    """Parst eine ganze Zahl, die echt größer als null sein muss."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("Der Wert muss größer als null sein.")
    return parsed


def positive_finite_float(value: str) -> float:
    """Parst eine endliche Fließkommazahl, die echt positiv sein muss."""
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError(
            "Der Wert muss eine endliche Zahl größer als null sein."
        )
    return parsed


def non_negative_finite_float(value: str) -> float:
    """Parst eine endliche Fließkommazahl, die nicht negativ sein darf."""
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError(
            "Der Wert muss eine endliche, nicht negative Zahl sein."
        )
    return parsed


def add_model_connection_arguments(parser: argparse.ArgumentParser) -> None:
    """Ergänzt die gemeinsamen Provider-Endpunkte und API-Key-Einstellung."""
    parser.add_argument(
        "--ollama-base-url",
        default="http://localhost:11434",
        help="Ollama-Basis-URL (Standard: %(default)s)",
    )
    parser.add_argument(
        "--ollama-num-ctx",
        type=positive_int,
        default=None,
        help=(
            "Ollama-Kontextgroesse pro Modellaufruf; ohne Angabe gilt der "
            "Modell- oder Serverstandard"
        ),
    )
    parser.add_argument(
        "--openai-base-url",
        default="https://api.openai.com/v1",
        help="OpenAI-API-Basis-URL (Standard: %(default)s)",
    )
    parser.add_argument(
        "--openai-api-key-env",
        default="OPENAI_API_KEY",
        help="Umgebungsvariable mit dem OpenAI-API-Key (Standard: %(default)s)",
    )


def add_model_arguments(
    parser: argparse.ArgumentParser,
    *,
    model_help: str,
) -> None:
    """Ergänzt Modell, Provider, Verbindung und Laufzeit einer Einzelstufe."""
    parser.add_argument("--model", required=True, help=model_help)
    parser.add_argument(
        "--provider",
        choices=MODEL_PROVIDERS,
        default="ollama",
        help="Modell-Provider (Standard: %(default)s)",
    )
    add_model_connection_arguments(parser)
    add_runtime_arguments(parser)


def add_prompt_argument(
    parser: argparse.ArgumentParser,
    *,
    prompt_default: Path,
    prompt_help: str,
) -> None:
    """Ergänzt die Promptdatei einer Modellstufe."""
    parser.add_argument(
        "--prompt-file",
        type=Path,
        default=prompt_default,
        help=f"{prompt_help} (Standard: %(default)s)",
    )


def add_runtime_arguments(
    parser: argparse.ArgumentParser,
    *,
    prefix: str = "",
    timeout_help: str = "Timeout pro Modellaufruf in Sekunden",
    temperature_help: str = "Modell-Temperatur",
) -> None:
    """Ergänzt Timeout und Temperatur für eine Modellstufe."""
    option_prefix = f"{prefix}-" if prefix else ""
    parser.add_argument(
        f"--{option_prefix}timeout",
        type=positive_finite_float,
        default=1800.0,
        help=f"{timeout_help} (Standard: %(default)s)",
    )
    parser.add_argument(
        f"--{option_prefix}temperature",
        type=non_negative_finite_float,
        default=None,
        help=(
            f"{temperature_help}; ohne Angabe gilt der Provider-/Modellstandard"
        ),
    )


def add_overwrite_argument(
    parser: argparse.ArgumentParser,
    *,
    help_text: str,
) -> None:
    """Ergänzt den einheitlichen Schalter zum Ignorieren vorhandener Ergebnisse."""
    parser.add_argument(
        "--overwrite", type=boolean_value, metavar="{true,false}",
        default=False, help=help_text,
    )



def add_common_document_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    """Ergänzt die Dokumenteingaben der Bewertung."""
    parser.add_argument(
        "--assignment-dir", type=Path, required=True,
        help="Ausgabeordner der partitionierten Aufgabenstellung",
    )
    parser.add_argument(
        "--student-solution-dir", type=Path, required=True,
        help="Ausgabeordner der partitionierten studentischen Lösung",
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True,
        help="Ausgabeordner für die erzeugten Ergebnisse und Berichte",
    )
    parser.add_argument(
        "--reference-solution-dir", type=Path,
        help="Optionaler Ausgabeordner der partitionierten Musterlösung",
    )
    parser.add_argument(
        "--rubrics-dir", type=Path,
        help="Optionaler Ausgabeordner der erzeugten Rubrics",
    )
    parser.add_argument(
        "--context", type=Path, action="append", default=[],
        help="Optionale Kontextdatei; für mehrere Dateien wiederholen",
    )
    parser.add_argument(
        "--context-map",
        type=Path,
        help=(
            "Optionales JSON-Manifest, das jeder bewertbaren Blattaufgabe "
            "eigene Kontextdateien zuordnet"
        ),
    )
    parser.add_argument(
        "--skip-target",
        action="append",
        default=[],
        metavar="TARGET_PATH",
        help=(
            "Bewertungsziel gezielt als runtime_failure überspringen; "
            "für mehrere Ziele wiederholen"
        ),
    )


def _add_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    *,
    help_text: str,
) -> argparse.ArgumentParser:
    """Erzeugt einen Unterbefehl mit deaktivierten Optionsabkürzungen."""
    command = subparsers.add_parser(
        name,
        help=help_text,
        description=help_text,
        allow_abbrev=False,
    )
    command.add_argument(
        "--verbose",
        type=boolean_value,
        metavar="{true,false}",
        default=True,
        help=(
            "Fortschritt und alle erzeugten oder gecachten Artefaktpfade ausgeben "
            "(Standard: aktiviert)"
        ),
    )
    return command


def _add_validate_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Definiert die modellfreie Prüfung eines Artefakt-Ordners."""
    command = _add_command(
        subparsers,
        "validate",
        help_text="Vorhandene GradingPipeline-Artefakte prüfen und Befunde ausgeben",
    )
    command.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Ordner mit den zu prüfenden GradingPipeline-Artefakten",
    )


def _add_extract_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Definiert die visuelle Extraktion eines PDF- oder Bilddokuments."""
    command = _add_command(subparsers, "extract", help_text="Bild oder PDF nach Markdown extrahieren")
    command.add_argument("--input", type=Path, required=True, help="PDF oder Bilddatei")
    command.add_argument("--output-dir", type=Path, required=True, help="Ausgabeordner")
    command.add_argument(
        "--document-type", choices=DOCUMENT_TYPES, required=True,
        help="Dokumenttyp: assignment, reference_solution oder student_solution",
    )
    add_model_arguments(command, model_help="Name des Vision-Modells")
    add_prompt_argument(
        command, prompt_default=DEFAULT_VISUAL_EXTRACTION_PROMPT_PATH,
        prompt_help="Prompt für die visuelle Extraktion",
    )
    command.add_argument(
        "--dpi", type=positive_int, default=220,
        help="Render-Auflösung für PDFs (Standard: %(default)s)",
    )
    add_overwrite_argument(command, help_text="Vorhandene Ergebnisse ignorieren und neu erzeugen")


def _add_prepare_images_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Definiert die modellfreie Erzeugung der Bildsupplemente."""

    command = _add_command(
        subparsers,
        "prepare-images",
        help_text="Bildsupplemente aus Reviewed- oder Raw-Visual-Extraction erzeugen",
    )
    command.add_argument(
        "--input", type=Path, required=True,
        help="Ausgabeordner der Visual Extraction",
    )
    command.add_argument(
        "--document-type", choices=DOCUMENT_TYPES, required=True,
        help="Dokumenttyp: assignment, reference_solution oder student_solution",
    )


def _add_extract_tasks_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Definiert die Extraktion vollständiger Aufgaben aus dem Markdown der Visual Extraction."""
    command = _add_command(
        subparsers, "extract-tasks",
        help_text="Vollständige Aufgaben per Textmodell aus dem Markdown der Visual Extraction extrahieren",
    )
    command.add_argument(
        "--input", type=Path, required=True,
        help="Ausgabeordner der visuellen Extraktion mit 03_vlm_export.raw.md",
    )
    command.add_argument(
        "--output-dir", type=Path, default=None,
        help=(
            "Separater Ausgabeordner der Aufgabenextraktion; "
            "ohne Angabe wird der Eingabeordner verwendet"
        ),
    )
    command.add_argument(
        "--document-type", choices=DOCUMENT_TYPES, required=True,
        help="Dokumenttyp: assignment, reference_solution oder student_solution",
    )
    add_model_arguments(command, model_help="Name des Textmodells")
    add_prompt_argument(
        command, prompt_default=DEFAULT_TASK_EXTRACTION_PROMPT_PATH,
        prompt_help="Prompt für die Aufgabenextraktion",
    )
    add_overwrite_argument(command, help_text="Vorhandene Aufgabenextraktion ignorieren und neu erzeugen")


def _add_partition_tasks_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Definiert die Partitionierung extrahierter Aufgaben in Unteraufgaben."""
    command = _add_command(
        subparsers, "partition-tasks",
        help_text="Bereits extrahierte Aufgaben per Textmodell in Unteraufgaben zerlegen",
    )
    command.add_argument(
        "--input", type=Path, required=True,
        help="Ausgabeordner der Aufgabenextraktion mit 04_task_extraction.raw.json",
    )
    command.add_argument(
        "--output-dir", type=Path, default=None,
        help=(
            "Separater Ausgabeordner der Aufgabenpartitionierung; "
            "ohne Angabe wird der Eingabeordner verwendet"
        ),
    )
    add_model_arguments(command, model_help="Name des Textmodells")
    add_prompt_argument(
        command, prompt_default=DEFAULT_TASK_PARTITIONING_PROMPT_PATH,
        prompt_help="Prompt für die Aufgabenpartitionierung",
    )
    add_overwrite_argument(command, help_text="Vorhandene Partitionierung ignorieren und neu erzeugen")


def _add_create_rubrics_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Definiert die Rubric-Erzeugung aus Aufgabenstellung und Musterlösung."""
    command = _add_command(
        subparsers, "create-rubrics",
        help_text="Rubrics aus strukturgleicher Aufgabenstellung und Musterlösung erzeugen",
    )
    command.add_argument(
        "--assignment-dir", type=Path, required=True,
        help="Ausgabeordner der partitionierten Aufgabenstellung",
    )
    command.add_argument(
        "--reference-solution-dir", type=Path, required=True,
        help="Ausgabeordner der partitionierten Musterlösung",
    )
    command.add_argument(
        "--output-dir", type=Path, required=True,
        help="Ausgabeordner für Strukturprüfung, Cache und Rubrics",
    )
    add_model_arguments(command, model_help="Textmodell für die Rubric-Erstellung")
    add_prompt_argument(
        command, prompt_default=DEFAULT_RUBRIC_PROMPT_PATH,
        prompt_help="Prompt für die Rubric-Erstellung",
    )
    add_overwrite_argument(command, help_text="Vorhandenen Rubric-Cache ignorieren und neu erzeugen")


def _add_grade_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Definiert die Bewertung einer strukturgleichen studentischen Lösung."""
    command = _add_command(
        subparsers, "grade",
        help_text="Eine strukturgleiche studentische Lösung bewerten",
    )
    add_common_document_arguments(command)
    command.add_argument("--student-id", help="Optionale Kennung für Ergebnisdateien und Berichte")
    add_model_arguments(command, model_help="Textmodell für die Bewertung")
    add_prompt_argument(
        command, prompt_default=DEFAULT_GRADING_PROMPT_PATH,
        prompt_help="Prompt für die Bewertung",
    )
    add_overwrite_argument(command, help_text="Vorhandenen Bewertungs-Cache ignorieren und neu erzeugen")


def _add_grade_with_images_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Definiert die ausdrücklich multimodale Bewertung mit Bildsupplementen."""

    command = _add_command(
        subparsers,
        "grade-with-images",
        help_text="Eine studentische Lösung mit manuell zugeordneten Bildsupplementen bewerten",
    )
    add_common_document_arguments(command)
    command.add_argument("--student-id", help="Optionale Kennung für Ergebnisdateien und Berichte")
    add_model_arguments(command, model_help="Vision-Modell für die Bewertung")
    add_prompt_argument(
        command,
        prompt_default=DEFAULT_IMAGE_GRADING_PROMPT_PATH,
        prompt_help="Prompt für die Bewertung mit Bildern",
    )
    add_overwrite_argument(
        command,
        help_text="Vorhandenen multimodalen Bewertungs-Cache ignorieren und neu erzeugen",
    )


def _add_grade_monolithic_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Definiert die unstrukturierte Bewertung dreier vollständiger Dokumente."""

    command = _add_command(
        subparsers,
        "grade-monolithic",
        help_text=(
            "Aufgabenstellung, Musterlösung und studentische Lösung in einem "
            "freien multimodalen Modellaufruf bewerten"
        ),
    )
    command.add_argument(
        "--input",
        type=Path,
        required=True,
        help=(
            "Ordner mit assignment, reference_solution und student_solution; "
            "jeder Unterordner muss genau ein PDF oder Bild enthalten"
        ),
    )
    command.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Ausgabeordner; ohne Angabe wird der Eingabeordner verwendet",
    )
    add_model_arguments(command, model_help="Vision-Modell für die monolithische Bewertung")
    add_prompt_argument(
        command,
        prompt_default=DEFAULT_MONOLITHIC_GRADING_PROMPT_PATH,
        prompt_help="Prompt für die monolithische Bewertung",
    )
    command.add_argument(
        "--dpi",
        type=positive_int,
        default=220,
        help="Render-Auflösung für PDFs (Standard: %(default)s)",
    )
    add_overwrite_argument(
        command,
        help_text="Vorhandene monolithische Bewertung ignorieren und neu erzeugen",
    )


def build_parser() -> argparse.ArgumentParser:
    """Erzeugt den vollständigen Parser der ``grading_pipeline``-Kommandozeile."""
    parser = argparse.ArgumentParser(
        description="Extrahiert und verarbeitet Dokumente mit lokalen oder bereitgestellten Modellen.",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_validate_command(subparsers)
    _add_extract_command(subparsers)
    _add_prepare_images_command(subparsers)
    _add_extract_tasks_command(subparsers)
    _add_partition_tasks_command(subparsers)
    _add_create_rubrics_command(subparsers)
    _add_grade_command(subparsers)
    _add_grade_with_images_command(subparsers)
    _add_grade_monolithic_command(subparsers)
    return parser
