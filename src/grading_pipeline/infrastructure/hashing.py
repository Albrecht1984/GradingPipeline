"""Deterministische SHA-256-Hilfsfunktionen fuer Texte und Dateien."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_text(content: str) -> str:
    """Berechnet den SHA-256-Hash eines UTF-8-kodierten Textes."""

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    """Berechnet den SHA-256-Hash einer Datei in speicherschonenden Bloecken."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
