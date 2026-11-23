"""Liest Aufgabenfelder einheitlich, ohne Quelldaten zu ändern."""

from __future__ import annotations

from typing import Any


def text_or_empty(value: Any) -> str:
    """Liefert einen String unverändert und für alle anderen Typen Leertext."""
    # Beispiel: "  Text  " bleibt unverändert, None oder 42 wird zu "".
    return value if isinstance(value, str) else ""


def node_text(node: dict[str, Any], field: str) -> str:
    """Liest ein Textfeld eines Aufgabenknotens; typfremde Werte gelten als leer."""
    # Beispiel: node_text({"title": "Analysis"}, "title") ergibt "Analysis".
    return text_or_empty(node.get(field))


def node_label(node: dict[str, Any], fallback: str) -> str:
    """Liefert ID, sichtbare Bezeichnung, Titel oder einen stabilen Ersatztext."""
    # Beispiel: Bei id=None und source_label="1 a)" lautet das Label "1 a)".
    return (
        node_text(node, "id").strip()
        or node_text(node, "source_label").strip()
        or node_text(node, "title").strip()
        or fallback
    )


def child_nodes(node: dict[str, Any], location: str) -> list[dict[str, Any]]:
    """Liest Unteraufgaben; fehlend oder null bedeutet eine leere Kinderliste."""
    children = node.get("subtasks")
    # Beispiel: {} und {"subtasks": None} beschreiben beide einen Knoten ohne Kinder.
    if children is None:
        return []
    # Beispiel: ["a"] ist unbrauchbar, [{"id": "a"}] ist eine gültige Kinderliste.
    if not isinstance(children, list) or any(
        not isinstance(child, dict) for child in children
    ):
        raise ValueError(
            f"{location}.subtasks ist keine Liste von Aufgabenobjekten."
        )
    return children


def joined_node_text(node: dict[str, Any], fields: tuple[str, ...]) -> str:
    """Verbindet die nichtleeren Textfelder eines Knotens zu Markdown."""
    # Beispiel: "Einleitung", None und "Aufgabe" werden zu "Einleitung\n\nAufgabe".
    return "\n\n".join(
        text.strip()
        for field in fields
        if (text := node_text(node, field)).strip()
    )


def structural_path(path: tuple[int, ...]) -> str:
    """Formatiert einen numerischen Baumpfad als lesbaren JSON-Pfad."""
    if not path:
        raise ValueError("Ein Strukturpfad darf nicht leer sein.")
    return f"tasks[{path[0]}]" + "".join(
        f".subtasks[{index}]" for index in path[1:]
    )
