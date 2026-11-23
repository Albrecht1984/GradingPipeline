"""Erzeugt deterministische Bildsupplemente aus den BBOX-Platzhaltern."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Any

from PIL import Image, ImageDraw

from grading_pipeline.infrastructure.hashing import sha256_file, sha256_text
from grading_pipeline.infrastructure.json_io import read_required_json_object, write_json
from grading_pipeline.infrastructure.pipeline_artifacts import preferred_reviewed_artifact


SUPPLEMENTS_DIRNAME = "03_image_supplements"
SUPPLEMENTS_MANIFEST_FILENAME = "manifest.json"
IMAGE_REFERENCE_FIELD = "image_supplement_refs"
DOCUMENT_TYPES = {"assignment", "reference_solution", "student_solution"}
DOCUMENT_TYPE_FILENAME_PREFIXES = {
    "assignment": "asg",
    "reference_solution": "ref",
    "student_solution": "stu",
}

PAGE_MARKER = re.compile(r"<!--\s*Seite\s+(?P<page>\d+)\s*-->")
OBJECT_MARKER = re.compile(
    r"\[OBJEKT\s*\|\s*BBOX:\s*"
    r"\(\s*(?P<x1>\d+(?:\.\d+)?)\s*,\s*(?P<y1>\d+(?:\.\d+)?)\s*"
    r"(?:\)\s*-\s*\(\s*|,\s*)"
    r"(?P<x2>\d+(?:\.\d+)?)\s*,\s*(?P<y2>\d+(?:\.\d+)?)\s*\)\s*\]"
)


@dataclass(frozen=True)
class ImageSupplementPreparation:
    """Beschreibt annotiertes Markdown und erzeugte Supplementartefakte."""

    markdown: str
    manifest_path: Path | None
    image_count: int


def prepare_document_image_supplements(
    document_dir: Path,
    *,
    document_type: str,
) -> ImageSupplementPreparation:
    """Erzeugt Supplemente bevorzugt aus Reviewed-, sonst aus Raw-Markdown."""

    document_dir = document_dir.resolve()
    source_path = preferred_reviewed_artifact(
        document_dir,
        raw_filename="03_vlm_export.raw.md",
        reviewed_filename="03_vlm_export.reviewed.md",
    )
    if not source_path.is_file():
        raise FileNotFoundError(f"Visual-Extraction-Markdown nicht gefunden: {source_path}")
    source_markdown = source_path.read_text(encoding="utf-8").strip()
    if not source_markdown:
        raise ValueError(f"Visual-Extraction-Markdown ist leer: {source_path}")
    return prepare_image_supplements(
        document_dir,
        source_markdown,
        document_type=document_type,
        source_markdown_path=source_path,
    )


def prepare_image_supplements(
    document_dir: Path,
    source_markdown: str,
    *,
    document_type: str,
    source_markdown_path: Path | None = None,
) -> ImageSupplementPreparation:
    """Schneidet markierte Objekte aus und vergibt dokumentweit eindeutige IDs."""

    source_markdown = source_markdown.strip()
    markers = list(OBJECT_MARKER.finditer(source_markdown))
    document_path = document_dir / "03_vlm_document.raw.json"
    if not markers and not document_path.is_file():
        return ImageSupplementPreparation(source_markdown, None, 0)

    if document_type not in DOCUMENT_TYPES:
        raise ValueError(f"Unbekannter Dokumenttyp fuer Bildsupplemente: {document_type!r}")

    document = read_required_json_object(
        document_path,
        label="Dokumentmanifest der Visual Extraction",
    )
    source_sha256 = _source_sha256(document)
    document_uid = source_sha256[:12]
    markdown_sha256 = sha256_text(source_markdown)
    extraction_uid = markdown_sha256[:12]
    image_namespace = f"{document_type}__{document_uid}__{extraction_uid}"
    pages = _page_records(document, document_dir)
    page_sections = list(PAGE_MARKER.finditer(source_markdown))
    if markers and not page_sections:
        raise ValueError(
            "Objektplatzhalter gefunden, aber das Visual-Extraction-Markdown "
            "enthaelt keine Seitenmarker."
        )

    supplements_dir = document_dir / SUPPLEMENTS_DIRNAME
    supplements_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    overview_records: list[dict[str, Any]] = []
    output_parts: list[str] = []
    cursor = 0

    for section_index, page_match in enumerate(page_sections):
        section_start = page_match.start()
        section_end = (
            page_sections[section_index + 1].start()
            if section_index + 1 < len(page_sections)
            else len(source_markdown)
        )
        output_parts.append(source_markdown[cursor:section_start])
        section = source_markdown[section_start:section_end]
        page_number = int(page_match.group("page"))
        page = pages.get(page_number)
        if page is None:
            raise ValueError(
                f"Seite {page_number} fehlt im Dokumentmanifest der Visual Extraction."
            )
        annotated, page_records, overview_record = _prepare_page_supplements(
            section=section,
            page_number=page_number,
            page=page,
            document_dir=document_dir,
            supplements_dir=supplements_dir,
            image_namespace=image_namespace,
            document_type=document_type,
            document_uid=document_uid,
        )
        output_parts.append(annotated)
        records.extend(page_records)
        overview_records.append(overview_record)
        cursor = section_end
    output_parts.append(source_markdown[cursor:])

    expected_paths = {
        (document_dir / str(record["path"])).resolve()
        for record in [*records, *overview_records]
    }
    for old_image in supplements_dir.glob("*.png"):
        if old_image.resolve() not in expected_paths:
            old_image.unlink()

    manifest_path = supplements_dir / SUPPLEMENTS_MANIFEST_FILENAME
    write_json(
        manifest_path,
        {
            "document_type": document_type,
            "source_document_sha256": source_sha256,
            "source_markdown": (
                source_markdown_path.name
                if source_markdown_path is not None
                else "03_vlm_export.raw.md"
            ),
            "source_markdown_sha256": markdown_sha256,
            "images": records,
            "overview_pages": overview_records,
        },
    )
    return ImageSupplementPreparation(
        markdown="".join(output_parts),
        manifest_path=manifest_path,
        image_count=len(records),
    )


def load_prepared_image_supplements(
    document_dir: Path,
    source_markdown: str,
    *,
    source_markdown_path: Path,
    document_type: str,
) -> ImageSupplementPreparation:
    """Prüft vorhandene Supplemente und ergänzt ihre IDs im Markdown."""

    source_markdown = source_markdown.strip()
    markers = list(OBJECT_MARKER.finditer(source_markdown))
    if not markers:
        return ImageSupplementPreparation(source_markdown, None, 0)

    manifest_path = document_dir / SUPPLEMENTS_DIRNAME / SUPPLEMENTS_MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise FileNotFoundError(
            "Bildsupplement-Manifest fehlt. Bitte zuerst `prepare-images` ausfuehren: "
            f"{manifest_path}"
        )
    manifest = read_required_json_object(
        manifest_path,
        label="Bildsupplement-Manifest",
    )
    expected_hash = sha256_text(source_markdown)
    if manifest.get("document_type") != document_type:
        raise ValueError(
            "Bildsupplement-Manifest hat einen anderen Dokumenttyp. "
            "Bitte `prepare-images` erneut ausfuehren."
        )
    if (
        manifest.get("source_markdown") != source_markdown_path.name
        or manifest.get("source_markdown_sha256") != expected_hash
    ):
        raise ValueError(
            "Bildsupplemente passen nicht zur verwendeten Visual-Extraction-Fassung. "
            "Bitte `prepare-images` erneut ausfuehren."
        )
    raw_records = manifest.get("images")
    if not isinstance(raw_records, list) or len(raw_records) != len(markers):
        raise ValueError(
            "Bildsupplement-Manifest und Objektmarker haben unterschiedliche Umfaenge. "
            "Bitte `prepare-images` erneut ausfuehren."
        )

    record_index = 0

    def replace(match: re.Match[str]) -> str:
        """Setzt die geprüfte Manifest-ID in einen Objektmarker ein."""

        nonlocal record_index
        record = raw_records[record_index]
        record_index += 1
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise ValueError("Bildsupplement-Manifest enthaelt einen ungueltigen Bildeintrag.")
        bbox = tuple(float(match.group(name)) for name in ("x1", "y1", "x2", "y2"))
        manifest_bbox = record.get("bbox_normalized")
        if not isinstance(manifest_bbox, list) or manifest_bbox != list(bbox):
            raise ValueError(
                "Bildsupplement-Manifest enthaelt abweichende BBOX-Koordinaten. "
                "Bitte `prepare-images` erneut ausfuehren."
            )
        x1, y1, x2, y2 = (_format_coordinate(value) for value in bbox)
        return (
            f"[OBJEKT | ID: {record['id']} | "
            f"BBOX: ({x1}, {y1})-({x2}, {y2})]"
        )

    annotated = OBJECT_MARKER.sub(replace, source_markdown)
    return ImageSupplementPreparation(annotated, manifest_path, len(raw_records))


def _page_records(
    document: dict[str, Any],
    document_dir: Path,
) -> dict[int, dict[str, Any]]:
    """Indiziert und validiert die Seiten aus dem Visual-Extraction-Manifest."""

    raw_pages = document.get("pages")
    if not isinstance(raw_pages, list):
        raise ValueError("Das Dokumentmanifest enthaelt keine gueltige Seitenliste.")
    result: dict[int, dict[str, Any]] = {}
    for raw_page in raw_pages:
        if not isinstance(raw_page, dict) or not isinstance(raw_page.get("page_no"), int):
            raise ValueError("Das Dokumentmanifest enthaelt einen ungueltigen Seiteneintrag.")
        image = raw_page.get("image")
        if not isinstance(image, dict) or not isinstance(image.get("path"), str):
            raise ValueError("Ein Seiteneintrag enthaelt keinen gueltigen Bildpfad.")
        image_path = _resolve_inside(document_dir, image["path"])
        if not image_path.is_file():
            raise FileNotFoundError(f"Gerendertes Seitenbild nicht gefunden: {image_path}")
        result[raw_page["page_no"]] = {**raw_page, "resolved_image_path": image_path}
    return result


def _source_sha256(document: dict[str, Any]) -> str:
    """Liest den vollständigen SHA-256-Hash des ursprünglichen Dokuments."""

    origin = document.get("origin")
    source_hash = origin.get("binary_hash_sha256") if isinstance(origin, dict) else None
    if (
        not isinstance(source_hash, str)
        or re.fullmatch(r"[0-9a-fA-F]{64}", source_hash) is None
    ):
        raise ValueError(
            "Das Dokumentmanifest enthaelt keinen gueltigen "
            "origin.binary_hash_sha256."
        )
    return source_hash.lower()


def _prepare_page_supplements(
    *,
    section: str,
    page_number: int,
    page: dict[str, Any],
    document_dir: Path,
    supplements_dir: Path,
    image_namespace: str,
    document_type: str,
    document_uid: str,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Erzeugt Ausschnitte, Marker und die BBOX-Übersicht einer Seite."""

    records: list[dict[str, Any]] = []
    image_path = page["resolved_image_path"]
    with Image.open(image_path) as page_image:
        width, height = page_image.size

        def replace(match: re.Match[str]) -> str:
            """Ersetzt einen Marker durch seine ID und schreibt den Bildausschnitt."""

            bbox = tuple(float(match.group(name)) for name in ("x1", "y1", "x2", "y2"))
            _validate_normalized_bbox(bbox, page_number)
            object_number = len(records) + 1
            image_id = (
                f"{image_namespace}__p{page_number:03d}__img{object_number:03d}"
            )
            pixel_bbox = _pixel_bbox(bbox, width=width, height=height)
            output_path = supplements_dir / _image_filename(
                document_type=document_type,
                document_uid=document_uid,
                page_number=page_number,
                object_number=object_number,
            )
            page_image.crop(pixel_bbox).save(output_path, format="PNG")
            relative_output = output_path.relative_to(document_dir).as_posix()
            records.append(
                {
                    "id": image_id,
                    "path": relative_output,
                    "source_page": page_number,
                    "bbox_normalized": list(bbox),
                    "bbox_pixels": list(pixel_bbox),
                    "source_page_image": image_path.relative_to(document_dir).as_posix(),
                    "sha256": sha256_file(output_path),
                }
            )
            values = ", ".join(_format_coordinate(value) for value in bbox)
            x1, y1, x2, y2 = values.split(", ")
            return (
                f"[OBJEKT | ID: {image_id} | "
                f"BBOX: ({x1}, {y1})-({x2}, {y2})]"
            )

        annotated = OBJECT_MARKER.sub(replace, section)
        overview_path = supplements_dir / f"overview_page_{page_number:03d}.png"
        overview_image = page_image.convert("RGB")
        drawing = ImageDraw.Draw(overview_image)
        for record in records:
            left, top, right, bottom = record["bbox_pixels"]
            drawing.rectangle(
                (left, top, right - 1, bottom - 1),
                outline=(255, 0, 0),
                width=1,
            )
        overview_image.save(overview_path, format="PNG")
    overview_record = {
        "source_page": page_number,
        "path": overview_path.relative_to(document_dir).as_posix(),
        "sha256": sha256_file(overview_path),
    }
    return annotated, records, overview_record


def _image_filename(
    *,
    document_type: str,
    document_uid: str,
    page_number: int,
    object_number: int,
) -> str:
    """Erzeugt einen kurzen, weiterhin dokumentweit eindeutigen PNG-Namen.

    Die vollstaendige, extraktionsspezifische Bild-ID bleibt im Manifest
    erhalten. Der physische Dateiname vermeidet dagegen redundante Angaben,
    damit auch tiefe Windows-Experimentpfade unter MAX_PATH bleiben.
    """

    prefix = DOCUMENT_TYPE_FILENAME_PREFIXES[document_type]
    return (
        f"{prefix}__{document_uid[:8]}__"
        f"p{page_number:03d}__i{object_number:03d}.png"
    )


def _validate_normalized_bbox(
    bbox: tuple[float, float, float, float],
    page_number: int,
) -> None:
    """Prüft die vom Extraktionsprompt geforderten normierten Koordinaten."""

    x1, y1, x2, y2 = bbox
    if any(not math.isfinite(value) or value < 0 or value > 1000 for value in bbox):
        raise ValueError(
            f"Seite {page_number}: BBOX-Koordinaten muessen zwischen 0 und 1000 liegen: {bbox}"
        )
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"Seite {page_number}: BBOX hat keine positive Flaeche: {bbox}")


def _pixel_bbox(
    bbox: tuple[float, float, float, float],
    *,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    """Skaliert normierte Seitenkoordinaten konservativ auf Bildpixel."""

    x1, y1, x2, y2 = bbox
    left = max(0, min(width - 1, math.floor(x1 * width / 1000)))
    top = max(0, min(height - 1, math.floor(y1 * height / 1000)))
    right = max(left + 1, min(width, math.ceil(x2 * width / 1000)))
    bottom = max(top + 1, min(height, math.ceil(y2 * height / 1000)))
    return left, top, right, bottom


def _resolve_inside(root: Path, relative_path: str) -> Path:
    """Löst einen relativen Artefaktpfad ausschließlich unterhalb seines Dokuments auf."""

    candidate = (root / relative_path).resolve()
    resolved_root = root.resolve()
    if candidate == resolved_root or not candidate.is_relative_to(resolved_root):
        raise ValueError(f"Artefaktpfad verlaesst den Dokumentordner: {relative_path}")
    return candidate


def _format_coordinate(value: float) -> str:
    """Formatiert ganzzahlige normierte Koordinaten ohne Dezimalteil."""

    return str(int(value)) if value.is_integer() else f"{value:g}"
