"""Freie monolithische Bewertung vollständiger Dokumentseiten."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Callable

from langchain_core.language_models import BaseChatModel

from grading_pipeline.extraction.rendering import IMAGE_MIMETYPES, RenderedPage, render_input
from grading_pipeline.infrastructure.json_io import write_json
from grading_pipeline.infrastructure.model_calls import (
    MultimodalImage,
    MultimodalImageGroup,
    invoke_multimodal_json_model,
)
from grading_pipeline.models.responses import response_artifact, response_text

from .images import stored_image_groups_match


ProgressCallback = Callable[[str], None]
SUPPORTED_INPUT_SUFFIXES = {".pdf", *IMAGE_MIMETYPES}
DOCUMENT_GROUPS = (
    ("assignment", "Aufgabenstellung"),
    ("reference_solution", "Offizielle Musterlösung"),
    ("student_solution", "Studentische Lösung"),
)


@dataclass(frozen=True)
class MonolithicGradingResult:
    """Verweist auf die schlanken Artefakte eines Gesamtbewertungslaufs."""

    output_dir: Path
    raw_text_path: Path
    response_path: Path
    input_path: Path
    images_path: Path
    page_count: int
    from_cache: bool


class MonolithicGradingPipeline:
    """Sendet drei vollständige Dokumente in genau einem freien Modellaufruf."""

    def __init__(
        self,
        model: BaseChatModel,
        *,
        prompt: str,
        dpi: int = 220,
        progress: ProgressCallback | None = None,
    ) -> None:
        """Legt Modell, Prompt und Auflösung für die Gesamtbewertung fest."""
        if not prompt.strip():
            raise ValueError("Der Prompt für die monolithische Bewertung ist leer.")
        if dpi < 72:
            raise ValueError("Die Render-Auflösung muss mindestens 72 dpi betragen.")
        self.model = model
        self.prompt = prompt.strip()
        self.dpi = dpi
        self.progress = progress or (lambda _message: None)

    def grade(
        self,
        *,
        input_dir: Path,
        output_dir: Path | None = None,
        overwrite: bool = False,
    ) -> MonolithicGradingResult:
        """Rendert die drei Eingaben und speichert die freie Modellantwort."""

        input_dir = input_dir.resolve()
        if not input_dir.is_dir():
            raise FileNotFoundError(f"Monolithischer Eingabeordner fehlt: {input_dir}")
        output_dir = (output_dir or input_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        input_path = output_dir / "02_monolithic_grading.input.md"
        images_path = output_dir / "02_monolithic_grading.images.json"
        response_path = output_dir / "02_monolithic_grading.response.json"
        raw_text_path = output_dir / "03_monolithic_grading.raw.txt"

        sources = {
            role: _single_document(input_dir / role, role=role)
            for role, _label in DOCUMENT_GROUPS
        }
        rendered = {
            role: render_input(
                sources[role],
                output_dir / "01_pages" / role,
                self.dpi,
            )
            for role, _label in DOCUMENT_GROUPS
        }
        groups = _image_groups(rendered)
        stored_input = _input_artifact(self.prompt, groups, output_dir)
        image_manifest = _image_manifest(sources, rendered, output_dir)

        if (
            not overwrite
            and raw_text_path.is_file()
            and raw_text_path.read_text(encoding="utf-8").strip()
            and response_path.is_file()
            and input_path.is_file()
            and input_path.read_text(encoding="utf-8") == stored_input
            and stored_image_groups_match(images_path, image_manifest)
        ):
            self.progress("Monolithische Bewertung aus vorhandenem Ergebnis übernommen.")
            return MonolithicGradingResult(
                output_dir=output_dir,
                raw_text_path=raw_text_path,
                response_path=response_path,
                input_path=input_path,
                images_path=images_path,
                page_count=sum(len(pages) for pages in rendered.values()),
                from_cache=True,
            )

        input_path.write_text(stored_input, encoding="utf-8")
        write_json(images_path, image_manifest)
        response, _started_at = invoke_multimodal_json_model(
            self.model,
            self.prompt,
            groups,
            progress=self.progress,
            heartbeat_label="Monolithische Bewertung beim Modell",
            result_label="Monolithische Bewertung",
            json_mode=False,
        )
        text = response_text(response).strip()
        if not text:
            raise RuntimeError("Das Modell lieferte eine leere Bewertung.")
        write_json(response_path, response_artifact(response))
        raw_text_path.write_text(text + "\n", encoding="utf-8")
        return MonolithicGradingResult(
            output_dir=output_dir,
            raw_text_path=raw_text_path,
            response_path=response_path,
            input_path=input_path,
            images_path=images_path,
            page_count=sum(len(pages) for pages in rendered.values()),
            from_cache=False,
        )


def _single_document(directory: Path, *, role: str) -> Path:
    """Erwartet genau ein unterstütztes Quelldokument je Rolle."""

    if not directory.is_dir():
        raise FileNotFoundError(f"Dokumentordner für {role} fehlt: {directory}")
    candidates = sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES
    )
    if len(candidates) != 1:
        raise ValueError(
            f"Dokumentordner für {role} muss genau eine unterstützte Datei "
            f"enthalten, gefunden: {len(candidates)}"
        )
    return candidates[0]


def _image_groups(
    rendered: dict[str, list[RenderedPage]],
) -> list[MultimodalImageGroup]:
    """Ordnet alle Seiten sichtbar und deterministisch nach Dokumentrolle."""

    return [
        MultimodalImageGroup(
            label=label,
            images=tuple(
                MultimodalImage(
                    image_id=f"{role}:page_{page.page_number:03d}",
                    path=page.path,
                )
                for page in rendered[role]
            ),
        )
        for role, label in DOCUMENT_GROUPS
    ]


def _input_artifact(
    prompt: str,
    groups: list[MultimodalImageGroup],
    output_dir: Path,
) -> str:
    """Dokumentiert Prompt und Seitenreihenfolge ohne Bildinhalt oder Hashes."""

    lines = [prompt.rstrip(), "", "---", "", "# Übergebene Bildgruppen", ""]
    for group in groups:
        lines.append(f"## {group.label}")
        lines.extend(
            f"- `{image.image_id}`: `{image.path.relative_to(output_dir).as_posix()}`"
            for image in group.images
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _image_manifest(
    sources: dict[str, Path],
    rendered: dict[str, list[RenderedPage]],
    output_dir: Path,
) -> dict[str, object]:
    """Beschreibt reproduzierbar die Quellen und tatsächlich gesendeten Seiten."""

    return {
        "groups": [
            {
                "role": role,
                "label": label,
                "source": str(sources[role]),
                "source_sha256": _sha256(sources[role]),
                "pages": [
                    {
                        "id": f"{role}:page_{page.page_number:03d}",
                        "path": page.path.relative_to(output_dir).as_posix(),
                        "width": page.width,
                        "height": page.height,
                    }
                    for page in rendered[role]
                ],
            }
            for role, label in DOCUMENT_GROUPS
        ],
    }


def _sha256(path: Path) -> str:
    """Berechnet den SHA-256-Hash des Dokuments in Blöcken."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
