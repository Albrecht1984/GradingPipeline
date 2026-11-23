"""Extrahiert Dokumentseiten visuell und erzeugt nachvollziehbare Seitenartefakte."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import shutil
import time
from typing import Any, Callable, Mapping

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from grading_pipeline.infrastructure.artifact_names import VISUAL_EXTRACTION_ARTIFACTS
from grading_pipeline.infrastructure.hashing import sha256_file
from grading_pipeline.infrastructure.json_io import write_json
from grading_pipeline.caching.visual_extraction import (
    load_visual_extraction_page_cache,
    visual_extraction_page_cache_identity,
)
from grading_pipeline.caching.common import write_cache_document
from grading_pipeline.models.metadata import model_identity, model_label
from grading_pipeline.models.responses import response_artifact, response_text
from grading_pipeline.infrastructure.model_calls import invoke_vision_model
from grading_pipeline.infrastructure.progress import ProgressHeartbeat
from .rendering import RenderedPage, render_input
from .image_supplements import prepare_image_supplements
from grading_pipeline.infrastructure.statistics import (
    write_model_call_statistics,
)


@dataclass(frozen=True)
class VisualExtractionResult:
    """Bündelt die Ergebnisse einer visuellen Extraktion."""

    output_dir: Path
    markdown_path: Path
    document_json_path: Path
    page_count: int
    from_cache: bool = False


@dataclass(frozen=True)
class VisionExtractionRunSetup:
    """Bündelt Quellen, Verzeichnisse, Seiten und Modellmetadaten eines Laufs."""

    source: Path
    output_dir: Path
    pages_dir: Path
    responses_dir: Path
    pages: list[RenderedPage]
    use_page_cache: bool
    render_dpi: int | None
    model_metadata: dict[str, object]
    extractor_metadata: dict[str, object]


@dataclass(frozen=True)
class VisionPageArtifacts:
    """Enthält sämtliche kanonischen Artefaktpfade einer gerenderten Seite."""

    raw_markdown: Path
    response: Path
    statistics: Path
    cache: Path


@dataclass(frozen=True)
class GeneratedVisionPage:
    """Bündelt Antwort, Markdown und Startzeit einer neu erzeugten Seite."""

    response: AIMessage
    markdown: str
    started_at: float


@dataclass(frozen=True)
class VisionPageOutcome:
    """Beschreibt Manifestdaten, Markdown und Cache-Status einer Seite."""

    record: dict[str, object]
    markdown: str
    from_cache: bool


@dataclass
class VisionExtractionState:
    """Sammelt Seitenergebnisse und erwartete Artefakte während eines Laufs."""

    page_records: list[dict[str, object]] = field(default_factory=list)
    markdown_pages: list[str] = field(default_factory=list)
    generated_pages: int = 0


class VisualExtractionPipeline:
    """Rendert Dokumente und transkribiert jede Seite mit einem Vision-Modell."""

    def __init__(
        self,
        model: BaseChatModel,
        prompt: str,
        dpi: int = 220,
        document_type: str | None = None,
        progress: Callable[[str], None] | None = None,
    ):
        """Konfiguriert Modell, Prompts, Rendering und Fortschrittsausgabe."""
        if not prompt.strip():
            raise ValueError("Der Extraktionsprompt darf nicht leer sein.")
        self.model = model
        self.prompt = prompt.strip()
        self.dpi = dpi
        self.document_type = document_type
        self.progress = progress or (lambda _message: None)

    def extract(
        self,
        source: Path,
        output_dir: Path,
        *,
        overwrite: bool = False,
        use_cache: bool = False,
    ) -> VisualExtractionResult:
        """Extrahiert alle Seiten und erzeugt Markdown sowie Dokumentmanifest."""
        run = self._prepare_vision_extraction_run(
            source=source,
            output_dir=output_dir,
            overwrite=overwrite,
            use_cache=use_cache,
        )
        state = VisionExtractionState()
        for page in run.pages:
            outcome = self._extract_page(run=run, page=page, state=state)
            state.page_records.append(outcome.record)
            state.markdown_pages.append(
                f"<!-- Seite {page.page_number} -->\n\n{outcome.markdown}"
            )
            if not outcome.from_cache:
                state.generated_pages += 1
        return self._finalize_vision_extraction_run(run=run, state=state)

    def _prepare_vision_extraction_run(
        self,
        *,
        source: Path,
        output_dir: Path,
        overwrite: bool,
        use_cache: bool,
    ) -> VisionExtractionRunSetup:
        """Prüft Pfade, rendert Seiten und bereitet die Laufverzeichnisse vor."""
        source = source.resolve()
        output_dir = output_dir.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Eingabedatei nicht gefunden: {source}")
        if source == output_dir or source.is_relative_to(output_dir):
            raise ValueError(
                "Der Ausgabeordner darf weder die Eingabedatei selbst noch "
                "einen ihrer uebergeordneten Ordner bezeichnen."
            )
        self.progress(f"Quelle: {source}")
        self.progress(f"Ausgabe: {output_dir}")
        model_name, base_url = model_label(self.model)
        self.progress(f"Modell: {model_name} ({base_url or 'Standardendpunkt'})")
        if use_cache and not overwrite:
            if output_dir.exists() and not output_dir.is_dir():
                raise NotADirectoryError(
                    f"Der Ausgabepfad ist keine Dateiablage: {output_dir}"
                )
            output_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._prepare_output_dir(output_dir, overwrite)

        pages_dir = output_dir / VISUAL_EXTRACTION_ARTIFACTS.pages_dir
        responses_dir = output_dir / VISUAL_EXTRACTION_ARTIFACTS.responses_dir
        responses_dir.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() == ".pdf":
            self.progress(f"Rendere PDF mit {self.dpi} dpi ...")
        else:
            self.progress("Bereite Bild fuer die Verarbeitung vor ...")
        pages = render_input(source, pages_dir, dpi=self.dpi)
        self.progress(f"{len(pages)} Seite(n) vorbereitet.")
        current_model_identity = model_identity(self.model, json_mode=False)
        render_dpi = self.dpi if source.suffix.lower() == ".pdf" else None
        return VisionExtractionRunSetup(
            source=source,
            output_dir=output_dir,
            pages_dir=pages_dir,
            responses_dir=responses_dir,
            pages=pages,
            use_page_cache=use_cache and not overwrite,
            render_dpi=render_dpi,
            model_metadata=current_model_identity,
            extractor_metadata=self._extractor_metadata(
                model_metadata=current_model_identity,
                render_dpi=render_dpi,
            ),
        )

    def _extract_page(
        self,
        *,
        run: VisionExtractionRunSetup,
        page: RenderedPage,
        state: VisionExtractionState,
    ) -> VisionPageOutcome:
        """Lädt eine Seite aus dem Cache oder delegiert ihre neue Extraktion."""
        artifacts = self._page_artifacts(run, page)
        page_prompt = self.prompt
        cache_identity = visual_extraction_page_cache_identity(
            image_path=page.path,
            prompt=page_prompt,
            model_identity=run.model_metadata,
            render_dpi=run.render_dpi,
        )
        markdown = self._load_cached_page(
            run=run,
            page=page,
            artifacts=artifacts,
            cache_identity=cache_identity,
        )
        from_cache = markdown is not None
        if markdown is None:
            generated = self._generate_page(
                page=page,
                total_pages=len(run.pages),
                image_bytes=page.path.read_bytes(),
                prompt=page_prompt,
            )
            self._write_generated_page(
                run=run,
                page=page,
                artifacts=artifacts,
                page_prompt=page_prompt,
                cache_identity=cache_identity,
                generated=generated,
            )
            markdown = generated.markdown
        return VisionPageOutcome(
            record=self._page_record(page=page, output_dir=run.output_dir),
            markdown=markdown,
            from_cache=from_cache,
        )

    def _page_artifacts(
        self,
        run: VisionExtractionRunSetup,
        page: RenderedPage,
    ) -> VisionPageArtifacts:
        """Leitet sämtliche Artefaktpfade einer Seite aus ihrer Nummer ab."""
        stem = f"page_{page.page_number:03d}"
        return VisionPageArtifacts(
            raw_markdown=run.responses_dir / f"{stem}.raw.md",
            response=run.responses_dir / f"{stem}.response.json",
            statistics=run.responses_dir / f"{stem}.statistics.json",
            cache=run.responses_dir / f"{stem}.cache.json",
        )

    def _load_cached_page(
        self,
        *,
        run: VisionExtractionRunSetup,
        page: RenderedPage,
        artifacts: VisionPageArtifacts,
        cache_identity: Mapping[str, Any],
    ) -> str | None:
        """Lädt den aktuellen Seitentext aus einem passenden Cache."""
        if not run.use_page_cache:
            return None
        markdown = load_visual_extraction_page_cache(
            metadata_path=artifacts.cache,
            raw_markdown_path=artifacts.raw_markdown,
            expected_identity=cache_identity,
        )
        if markdown is None:
            return None
        self.progress(
            f"Seite {page.page_number}/{len(run.pages)}: Visual-Extraction-Cache-Treffer."
        )
        return markdown

    def _generate_page(
        self,
        *,
        page: RenderedPage,
        total_pages: int,
        image_bytes: bytes,
        prompt: str,
    ) -> GeneratedVisionPage:
        """Erzeugt den Seitentext und weist auf leeres Markdown hin."""
        size_mb = len(image_bytes) / (1024 * 1024)
        self.progress(
            f"Seite {page.page_number}/{total_pages}: sende Bild "
            f"({page.width}x{page.height}, {size_mb:.1f} MB) an den Provider. "
            "Beim ersten Aufruf kann das Laden des Modells mehrere "
            "Minuten dauern ..."
        )
        started_at = time.perf_counter()
        with ProgressHeartbeat(
            self.progress,
            label=f"Seite {page.page_number}/{total_pages}: Modellverarbeitung",
        ):
            response = invoke_vision_model(self.model, prompt, image_bytes)
        duration = time.perf_counter() - started_at
        markdown = strip_outer_markdown_fence(
            response_text(response)
        ).strip()
        if not markdown:
            self.progress(
                f"Hinweis: Seite {page.page_number}: Seitentext ist leer; "
                "bitte bei Bedarf manuell pruefen."
            )
        self.progress(
            f"Seite {page.page_number}/{total_pages}: Antwort nach "
            f"{duration:.1f} s erhalten ({len(markdown)} Zeichen)."
        )
        return GeneratedVisionPage(
            response=response,
            markdown=markdown,
            started_at=started_at,
        )

    def _write_generated_page(
        self,
        *,
        run: VisionExtractionRunSetup,
        page: RenderedPage,
        artifacts: VisionPageArtifacts,
        page_prompt: str,
        cache_identity: Mapping[str, Any],
        generated: GeneratedVisionPage,
    ) -> None:
        """Schreibt Modellantwort, Statistik und Cache einer neu erzeugten Seite."""
        artifacts.raw_markdown.write_text(
            generated.markdown + "\n", encoding="utf-8"
        )
        write_json(artifacts.response, response_artifact(generated.response))
        write_model_call_statistics(
            artifacts.statistics,
            model=self.model,
            response=generated.response,
            stage="visual_extraction",
            model_input=page_prompt,
            output_text=generated.markdown,
            started_at=generated.started_at,
            complexity={
                "image_width": page.width,
                "image_height": page.height,
            },
            json_mode=False,
            warn=self.progress,
        )
        write_cache_document(
            artifacts.cache,
            metadata=cache_identity,
        )
        self.progress(
            f"Seite {page.page_number}/{len(run.pages)}: Rohdaten gespeichert."
        )

    def _finalize_vision_extraction_run(
        self,
        *,
        run: VisionExtractionRunSetup,
        state: VisionExtractionState,
    ) -> VisualExtractionResult:
        """Bereinigt Altartefakte und schreibt Sammel-Markdown sowie Manifest."""
        self.progress("Fuege Seiten-Markdown zusammen ...")
        combined_markdown = "\n\n".join(state.markdown_pages).strip() + "\n"
        markdown_path = run.output_dir / VISUAL_EXTRACTION_ARTIFACTS.markdown
        markdown_path.write_text(combined_markdown, encoding="utf-8")
        document_json_path = run.output_dir / VISUAL_EXTRACTION_ARTIFACTS.document_json
        document_payload = {
            "name": run.source.stem,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "origin": {
                "filename": run.source.name,
                "binary_hash_sha256": sha256_file(run.source),
            },
            "extractor": {**run.extractor_metadata},
            "pages": state.page_records,
        }
        write_json(document_json_path, document_payload)
        if self.document_type is not None:
            supplements = prepare_image_supplements(
                run.output_dir,
                combined_markdown,
                document_type=self.document_type,
                source_markdown_path=markdown_path,
            )
            self.progress(
                f"Bildsupplemente erzeugt: {supplements.image_count} Bild(er) | "
                f"{supplements.manifest_path}"
            )
        self.progress("Extraktion abgeschlossen.")
        return VisualExtractionResult(
            output_dir=run.output_dir,
            markdown_path=markdown_path,
            document_json_path=document_json_path,
            page_count=len(run.pages),
            from_cache=state.generated_pages == 0,
        )

    def _extractor_metadata(
        self,
        *,
        model_metadata: dict[str, object],
        render_dpi: int | None,
    ) -> dict[str, object]:
        """Beschreibt Modell, Rendering und Prompt für das Dokumentmanifest."""
        metadata = {
            key: value for key, value in model_metadata.items()
            if key not in {"base_url", "response_format"}
        }
        metadata.update(render_dpi=render_dpi, prompt=self.prompt)
        return metadata

    def _prepare_output_dir(self, output_dir: Path, overwrite: bool) -> None:
        """Prüft den Ausgabeordner und ersetzt ihn bei explizitem Überschreiben."""
        if output_dir.exists() and not output_dir.is_dir():
            raise NotADirectoryError(f"Der Ausgabepfad ist keine Dateiablage: {output_dir}")
        if output_dir.exists() and any(output_dir.iterdir()):
            if not overwrite:
                raise FileExistsError(
                    f"Der Ausgabeordner ist nicht leer: {output_dir}. "
                    "Nutze --overwrite zum Ersetzen."
                )
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    def _page_record(
        self,
        page: RenderedPage,
        output_dir: Path,
    ) -> dict[str, object]:
        """Erzeugt den serialisierbaren Manifesteintrag einer Seite."""
        return {
            "page_no": page.page_number,
            "image": {
                "path": page.path.relative_to(output_dir).as_posix(),
                "width": page.width,
                "height": page.height,
            },
        }

def strip_outer_markdown_fence(text: str) -> str:
    """Entfernt eine äußere Markdown-Codeklammer und Randleerzeichen aus einer Modellantwort."""
    stripped = text.strip()
    if not stripped.startswith("```") or not stripped.endswith("```"):
        return stripped
    first_newline = stripped.find("\n")
    if first_newline == -1:
        return stripped
    return stripped[first_newline + 1 : -3].strip()
