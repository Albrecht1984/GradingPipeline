"""Lädt manuell referenzierte Bildsupplemente für das Vision-Grading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from grading_pipeline.extraction.image_supplements import (
    IMAGE_REFERENCE_FIELD,
    SUPPLEMENTS_DIRNAME,
    SUPPLEMENTS_MANIFEST_FILENAME,
)
from grading_pipeline.infrastructure.hashing import sha256_file
from grading_pipeline.infrastructure.json_io import (
    read_cache_json_object,
    read_required_json_object,
)


IMAGE_GROUP_ORDER = ("assignment", "reference_solution", "student_solution")
IMAGE_GROUP_LABELS = {
    "assignment": "AUFGABENSTELLUNG",
    "reference_solution": "MUSTERLOESUNG",
    "student_solution": "STUDENTISCHE_LOESUNG",
}


@dataclass(frozen=True)
class GradingImage:
    """Beschreibt ein geprüftes Bild und seine Rolle im Bewertungsmaterial."""

    image_id: str
    source_role: str
    path: Path
    sha256: str


@dataclass(frozen=True)
class GradingImageGroup:
    """Bündelt alle Bilder genau einer Quelle in fester Request-Reihenfolge."""

    source_role: str
    images: tuple[GradingImage, ...]

    @property
    def label(self) -> str:
        """Liefert die sichtbare Quellenbezeichnung der Bildgruppe."""

        return IMAGE_GROUP_LABELS[self.source_role]


def stored_image_groups_match(path: Path, expected: dict[str, object]) -> bool:
    """Vergleicht die gespeicherten Bildgruppen einschließlich ihrer Reihenfolge."""

    stored = read_cache_json_object(path)
    return stored is not None and stored.get("groups") == expected["groups"]


def collect_grading_image_groups(
    *,
    assignment: dict[str, Any],
    assignment_dir: Path,
    student_solution: dict[str, Any],
    student_solution_dir: Path,
    reference_solution: dict[str, Any] | None,
    reference_solution_dir: Path | None,
    task_path: tuple[int, ...],
) -> list[GradingImageGroup]:
    """Löst referenzierte Bilder als explizite, fest geordnete Quellgruppen auf."""

    sources: dict[str, tuple[dict[str, Any], Path]] = {
        "assignment": (assignment, assignment_dir),
        "student_solution": (student_solution, student_solution_dir),
    }
    if reference_solution is not None and reference_solution_dir is not None:
        sources["reference_solution"] = (reference_solution, reference_solution_dir)
    groups: list[GradingImageGroup] = []
    for source_role in IMAGE_GROUP_ORDER:
        source = sources.get(source_role)
        if source is None:
            continue
        document, document_dir = source
        refs = _refs_for_path(document, task_path, source_role=source_role)
        if refs:
            groups.append(
                GradingImageGroup(
                    source_role=source_role,
                    images=tuple(
                        _resolve_references(
                            refs,
                            document_dir=document_dir,
                            source_role=source_role,
                        )
                    ),
                )
            )
    return groups


def _refs_for_path(
    document: dict[str, Any],
    task_path: tuple[int, ...],
    *,
    source_role: str,
) -> list[str]:
    """Sammelt Referenzen des Blattes und seiner Vorfahren ohne globale Prüfungen."""

    nodes = document.get("tasks")
    collected: list[str] = []
    for depth, index in enumerate(task_path):
        if not isinstance(nodes, list) or index >= len(nodes):
            raise ValueError(
                f"Bildsupplemente: ungueltiger Aufgabenpfad in {source_role}: {task_path}"
            )
        node = nodes[index]
        if not isinstance(node, dict):
            raise ValueError(
                f"Bildsupplemente: Aufgabenknoten in {source_role} ist kein Objekt."
            )
        if IMAGE_REFERENCE_FIELD in node:
            refs = node[IMAGE_REFERENCE_FIELD]
            if not isinstance(refs, list) or any(
                not isinstance(ref, str) or not ref.strip() for ref in refs
            ):
                raise ValueError(
                    f"{source_role}, Ebene {depth}: {IMAGE_REFERENCE_FIELD} muss "
                    "eine Liste nichtleerer Bild-IDs sein."
                )
            collected.extend(ref.strip() for ref in refs)
        nodes = node.get("subtasks")
    return list(dict.fromkeys(collected))


def _resolve_references(
    refs: list[str],
    *,
    document_dir: Path,
    source_role: str,
) -> list[GradingImage]:
    """Prüft ausschließlich angeforderte IDs gegen das lokale Manifest."""

    supplements_dir = (document_dir / SUPPLEMENTS_DIRNAME).resolve()
    manifest_path = supplements_dir / SUPPLEMENTS_MANIFEST_FILENAME
    manifest = read_required_json_object(
        manifest_path,
        label=f"Bildsupplement-Manifest ({source_role})",
    )
    raw_images = manifest.get("images")
    if not isinstance(raw_images, list):
        raise ValueError(f"Bildsupplement-Manifest enthaelt keine images-Liste: {manifest_path}")
    by_id = {
        item.get("id"): item
        for item in raw_images
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    result: list[GradingImage] = []
    for image_id in refs:
        item = by_id.get(image_id)
        if item is None:
            raise ValueError(
                f"Referenziertes Bildsupplement {image_id!r} fehlt im Manifest: {manifest_path}"
            )
        relative_path = item.get("path")
        expected_hash = item.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
            raise ValueError(f"Bildsupplement {image_id!r} hat unvollstaendige Metadaten.")
        path = (document_dir / relative_path).resolve()
        if path == supplements_dir or not path.is_relative_to(supplements_dir):
            raise ValueError(
                f"Bildsupplement {image_id!r} liegt ausserhalb von {SUPPLEMENTS_DIRNAME}."
            )
        if not path.is_file():
            raise FileNotFoundError(f"Referenziertes Bildsupplement fehlt: {path}")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise ValueError(f"Pruefsumme des Bildsupplements stimmt nicht: {path}")
        result.append(
            GradingImage(
                image_id=image_id,
                source_role=source_role,
                path=path,
                sha256=actual_hash,
            )
        )
    return result
