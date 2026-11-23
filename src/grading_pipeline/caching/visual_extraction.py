"""Cache-Verwaltung fuer einzelne Seiten der visuellen Extraktion."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .common import read_matching_cache
from grading_pipeline.infrastructure.hashing import sha256_file, sha256_text


def visual_extraction_page_cache_identity(
    *,
    image_path: Path,
    prompt: str,
    model_identity: Mapping[str, Any],
    render_dpi: int | None,
) -> dict[str, Any]:
    """Erzeugt die Cache-Identitaet einer gerenderten und extrahierten Seite."""

    return {
        "image_sha256": sha256_file(image_path),
        "prompt_sha256": sha256_text(prompt),
        "render_dpi": render_dpi,
        "model": dict(model_identity),
    }


def load_visual_extraction_page_cache(
    *,
    metadata_path: Path,
    raw_markdown_path: Path,
    expected_identity: Mapping[str, Any],
) -> str | None:
    """Lädt den aktuellen Seitentext, wenn seine unveränderte Eingabe zum Cache passt."""

    if not raw_markdown_path.is_file():
        return None
    if read_matching_cache(
        metadata_path,
        metadata=expected_identity,
    ) is None:
        return None
    try:
        return raw_markdown_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
