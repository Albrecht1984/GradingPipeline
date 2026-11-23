"""Bereitet PDF- und Bilddateien als nummerierte Seitenartefakte vor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil


IMAGE_MIMETYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


@dataclass(frozen=True)
class RenderedPage:
    """Beschreibt eine einsbasiert nummerierte, vorbereitete Dokumentseite."""

    page_number: int
    path: Path
    width: int
    height: int


def render_input(source: Path, pages_dir: Path, dpi: int = 220) -> list[RenderedPage]:
    """Bereitet eine PDF- oder Bilddatei im angegebenen Seitenordner vor.

    PDFs werden vollständig und einsbasiert nummeriert als PNG gerendert.
    Unterstützte Einzelbilder werden unverändert unter einem normalisierten
    Seitennamen kopiert. Gleichnamige Zieldateien werden überschrieben;
    andere vorhandene Dateien im Seitenordner bleiben unberührt.

    Args:
        source: Pfad zur vorhandenen PDF- oder Bilddatei.
        pages_dir: Zielordner für die vorbereiteten Seitenbilder.
        dpi: Renderauflösung für PDFs; mindestens 72 dpi.

    Returns:
        Die vorbereiteten Seiten in ihrer Dokumentreihenfolge.

    Raises:
        FileNotFoundError: Wenn ``source`` keine vorhandene Datei ist.
        ValueError: Bei zu geringer Auflösung oder nicht unterstützter Endung.
        RuntimeError: Wenn die benötigte PyMuPDF-Abhängigkeit fehlt.
    """
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Eingabedatei nicht gefunden: {source}")
    if dpi < 72:
        raise ValueError("Die Render-Aufloesung muss mindestens 72 dpi betragen.")

    pages_dir.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        return _render_pdf(source, pages_dir, dpi)
    if suffix in IMAGE_MIMETYPES:
        return [_copy_image(source, pages_dir)]
    supported = ", ".join([".pdf", *sorted(IMAGE_MIMETYPES)])
    raise ValueError(f"Nicht unterstuetztes Eingabeformat {suffix!r}. Erlaubt: {supported}")


def _render_pdf(source: Path, pages_dir: Path, dpi: int) -> list[RenderedPage]:
    """Rendert alle PDF-Seiten als RGB-PNG."""
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF fehlt. Installiere die Abhaengigkeiten aus requirements.txt."
        ) from exc

    document = fitz.open(source)
    try:
        if document.page_count == 0:
            raise ValueError(f"Das PDF enthaelt keine Seiten: {source}")
        scale = dpi / 72.0
        matrix = fitz.Matrix(scale, scale)
        pages: list[RenderedPage] = []
        for index, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            target = pages_dir / f"page_{index:03d}.png"
            pixmap.save(target)
            pages.append(
                RenderedPage(
                    page_number=index,
                    path=target,
                    width=pixmap.width,
                    height=pixmap.height,
                )
            )
        return pages
    finally:
        document.close()


def _copy_image(source: Path, pages_dir: Path) -> RenderedPage:
    """Kopiert ein Einzelbild samt Metadaten und ermittelt seine Pixelmaße."""
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF fehlt. Installiere die Abhaengigkeiten aus requirements.txt."
        ) from exc

    target = pages_dir / f"page_001{source.suffix.lower()}"
    shutil.copy2(source, target)
    pixmap = fitz.Pixmap(str(source))
    try:
        return RenderedPage(
            page_number=1,
            path=target,
            width=pixmap.width,
            height=pixmap.height,
        )
    finally:
        pixmap = None
