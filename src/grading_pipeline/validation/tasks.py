"""Prüft extrahierte und partitionierte Aufgabenstrukturen, ohne sie zu verändern."""

from __future__ import annotations

from typing import Any, Callable, Iterator

from grading_pipeline.infrastructure.task_nodes import child_nodes, node_text, text_or_empty
from .numbers import parse_optional_positive_points


DOCUMENT_TYPES = (
    "assignment",
    "reference_solution",
    "student_solution",
)
NULL_LIKE_OPTIONAL_TEXT = {"null", "none", "n/a"}


def _null_literals(document: dict[str, Any]) -> Iterator[tuple[str, str]]:
    """Liefert Feldpfad und Text für Platzhalter wie ``null``, ``NONE`` oder ``n/a``.

    Beispiel: ``{"document_title": "null", "tasks": [{"title": " n/a "}]}``
    liefert ``("document_title", "null")`` und ``("tasks[0].title", " n/a ")``.
    """
    def visit(node: dict[str, Any], path: str, fields: tuple[str, ...]) -> Iterator[tuple[str, str]]:
        """Prüft optionale Texte und durchläuft vorhandene Aufgaben rekursiv."""
        for field in fields:
            value = node.get(field)
            if isinstance(value, str) and value.strip().lower() in NULL_LIKE_OPTIONAL_TEXT:
                yield f"{path}{field}", value
        child_field = "tasks" if not path else "subtasks"
        children = node.get(child_field)
        if isinstance(children, list):
            for index, child in enumerate(children):
                if isinstance(child, dict):
                    yield from visit(child, f"{path}{child_field}[{index}].", ("source_label", "title"))

    yield from visit(document, "", ("document_title",))


def warn_extraction_content(document: dict[str, Any], *, warn: Callable[[str], None]) -> None:
    """Gibt Inhaltswarnungen direkt aus; sammelt nichts und verändert keine Werte."""
    from .structure import warn_ids

    for location, value in _null_literals(document):
        warn(f"WARNUNG: {location} enthaelt {value!r} statt JSON-null.")
    warn_ids(document, document["document_type"], warn=warn)

def validate_tasks(
    data: dict[str, Any],
    expected_document_type: str | None = None,
    *,
    warn: Callable[[str], None] | None = None,
) -> None:
    """Prüft das Datenformat der extrahierten Hauptaufgaben vor der Partitionierung.

    Jeder Eintrag in ``data["tasks"]`` steht für eine Hauptaufgabe, etwa
    „Aufgabe 1“. Je nach Dokumenttyp enthält sein ``markdown`` die Aufgabenstellung,
    die zugehörige Musterlösung oder die studentische Bearbeitung einschließlich
    aller Teilaufgaben beziehungsweise Teillösungen. Eine Hauptaufgabe kann mehrere
    Seiten umfassen. Erst die spätere Partitionierung gliedert ihren Inhalt in
    ``subtasks``.

    Geprüft werden der Dokumenttyp, die Texttypen der optionalen Titel und
    Bezeichnungen sowie eine nichtleere Aufgabenliste aus JSON-Objekten.
    Unbrauchbare IDs und optionale Metadaten sowie leerer oder fehlender Text und
    fehlende oder unbrauchbare Punktwerte werden nur gemeldet. Markdown muss Text
    oder null sein. Bei Musterlösungen und studentischen Bearbeitungen werden auch
    verwendbare Zahlenwerte gemeldet, weil dort ``null`` erwartet wird.
    Die Prüfung stellt keine inhaltliche Richtigkeit oder Vollständigkeit fest
    und verändert die übergebenen Daten nicht.

    Args:
        data: Bereits geparstes Dokumentobjekt mit ``document_type`` und ``tasks``.
        expected_document_type: Optional vorgegebener Dokumenttyp. Wenn gesetzt,
            muss er mit dem Typ im Dokument übereinstimmen.
        warn: Empfänger direkter Konsolenwarnungen; ohne Empfänger keine Ausgabe.

    Raises:
        ValueError: Beim ersten ungültigen Dokumenttyp oder Aufgabenformat.
    """
    _validate_main_tasks(
        data,
        expected_document_type=expected_document_type,
        partitioned=False,
        warn=warn,
    )


def validate_partitioned_tasks(
    data: dict[str, Any],
    expected_document_type: str | None = None,
    *,
    warn: Callable[[str], None] | None = None,
) -> None:
    """Prüft Hauptaufgaben nach ihrer Gliederung in Unteraufgaben (Partitionierung).

    Fehlende Inhalte werden direkt gemeldet, ohne die Prüfung abzubrechen.
    Geprüft werden Dokumenttyp, Aufgabenliste, Metadaten und Punktwerte
    sowie rekursiv die Unteraufgaben und deren Inhalt. Punktwerte sind nur bei
    Aufgabenstellungen (assignment) vorgesehen; Zahlenwerte in Lösungen erzeugen Warnungen.
    Die Prüfung bestätigt keine inhaltliche Richtigkeit oder Vollständigkeit.

    Args:
        data: Bereits geparstes Dokumentobjekt mit ``document_type`` und ``tasks``.
        expected_document_type: Optional vorgegebener Dokumenttyp, mit dem der
            Typ im Dokument übereinstimmen muss.
        warn: Empfänger direkter Warnungen, auch aus rekursiven Unteraufgabenprüfungen.

    Raises:
        ValueError: Beim ersten ungültigen Dokumenttyp oder Aufgabenformat.
    """
    _validate_main_tasks(
        data,
        expected_document_type=expected_document_type,
        partitioned=True,
        warn=warn,
    )


def _validate_main_tasks(
    data: dict[str, Any],
    *,
    expected_document_type: str | None,
    partitioned: bool,
    warn: Callable[[str], None] | None,
) -> None:
    """Prüft technische Dokument- und Baumstruktur; Qualität nur bei ``warn``."""
    document_type = validate_document_type(data, expected_document_type)
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        description = (
            "partitionierten Hauptaufgaben" if partitioned else "Hauptaufgaben"
        )
        raise ValueError(f"Die LLM-Antwort enthaelt keine {description}.")
    for index, task in enumerate(tasks, start=1):
        location = f"Hauptaufgabe {index}"
        if not isinstance(task, dict):
            raise ValueError(f"{location} ist kein JSON-Objekt.")
        if partitioned:
            _validate_partitioned_task_structure(task, location)
    if warn is not None:
        warn_task_quality(data, partitioned=partitioned, warn=warn)


def _validate_partitioned_task_structure(task: dict[str, Any], location: str) -> None:
    """Fordert rekursiv nur Objektknoten und verwendbare Kinderlisten."""
    for index, subtask in enumerate(child_nodes(task, location), start=1):
        child_location = f"{location}, Unteraufgabe {index}"
        if not isinstance(subtask, dict):
            raise ValueError(f"{child_location} ist kein JSON-Objekt.")
        _validate_partitioned_task_structure(subtask, child_location)


def warn_task_quality(
    data: dict[str, Any], *, partitioned: bool, warn: Callable[[str], None]
) -> None:
    """Meldet Text-, Metadaten- und Punktprobleme eines technisch lesbaren Dokuments."""
    document_type = data["document_type"]
    _optional_text(data.get("document_title"), "document_title", warn=warn)
    allow_points = document_type == "assignment"
    for index, task in enumerate(data["tasks"], start=1):
        location = f"Hauptaufgabe {index}"
        validate_task_metadata(task, location, warn=warn)
        _validate_points_policy(task, location, allow_points=allow_points, warn=warn)
        if partitioned:
            _validate_partitioned_task_content(
                task, location=location, allow_points=allow_points, warn=warn
            )
        else:
            markdown = _optional_text(
                task.get("markdown"), f"{location}.markdown", warn=warn
            )
            if not markdown.strip():
                warn(f"WARNUNG: {location} enthaelt keinen Text.")


def _validate_partitioned_task_content(
    task: dict[str, Any],
    *,
    location: str,
    allow_points: bool,
    warn: Callable[[str], None] | None = None,
) -> None:
    """Prüft Unteraufgaben und Texttypen; meldet fehlenden Inhalt ohne Abbruch."""
    subtasks = child_nodes(task, location)
    for index, subtask in enumerate(subtasks, start=1):
        validate_subtask(
            subtask,
            location=f"{location}, Unteraufgabe {index}",
            allow_points=allow_points,
            warn=warn,
        )
    introduction = _optional_text(
        task.get("introduction_markdown"),
        f"{location}.introduction_markdown",
        warn=warn,
    )
    closing = _optional_text(
        task.get("closing_markdown"),
        f"{location}.closing_markdown",
        warn=warn,
    )
    if not (introduction.strip() or subtasks or closing.strip()) and warn is not None:
        warn(f"WARNUNG: {location} enthaelt keinen Inhalt.")


def validate_document_type(
    data: dict[str, Any],
    expected_document_type: str | None = None,
) -> str:
    """Prüft den Dokumenttyp und optional dessen erwarteten festen Wert."""
    document_type = data.get("document_type")
    if document_type not in DOCUMENT_TYPES:
        raise ValueError("Die LLM-Antwort enthaelt keinen gueltigen document_type.")
    if expected_document_type is not None and document_type != expected_document_type:
        raise ValueError("Das Modell hat den document_type veraendert.")
    return document_type


def validate_task_metadata(
    task: dict[str, Any],
    location: str,
    *,
    warn: Callable[[str], None] | None = None,
) -> None:
    """Prüft Metadaten, ohne sie zu verändern:

    - id: "2" oder "Aufgabe 2" unauffällig; fehlend, null, 2, "" und "  " werden gemeldet.
    - source_label/title: Text, null oder fehlend unauffällig; andere Typen werden gemeldet.
    - points: null, 2 oder 2.5 unauffällig; fehlend, 0, -1, "2", True und NaN/Inf
      werden gemeldet und unverändert belassen.
    """
    if not node_text(task, "id").strip() and warn is not None:
        warn(f"WARNUNG: {location}.id ist kein nichtleerer Text.")
    _optional_text(
        task.get("source_label"), f"{location}.source_label", warn=warn
    )
    _optional_text(task.get("title"), f"{location}.title", warn=warn)
    validate_points(task, location, warn=warn)


def validate_preserved_task_metadata(
    source: dict[str, Any],
    partitioned: dict[str, Any],
    *,
    location: str,
    warn: Callable[[str], None] | None = None,
) -> None:
    """Meldet geänderte id/source_label/title/points, ohne Werte zurückzusetzen.

    Beispiel: points=3 in der Quelle und points=4 im Ergebnis erzeugt eine
    Warnung; 4 bleibt erhalten. Identische Werte erzeugen keine Warnung.
    """
    # Dieselbe Hauptaufgabe vor/nach der Partitionierung vergleichen:
    # z. B. 10 → 12 Punkte nur melden; mit 12 weiterarbeiten, Quelle unverändert lassen.
    for field in ("id", "source_label", "title", "points"):
        if partitioned.get(field) != source.get(field) and warn is not None:
            warn(
                f"WARNUNG: {location}.{field} wurde beim Partitionieren veraendert: "
                f"Quelle {source.get(field)!r}, Ergebnis {partitioned.get(field)!r}."
            )


def validate_subtask(
    subtask: Any,
    location: str,
    *,
    allow_points: bool = True,
    warn: Callable[[str], None] | None = None,
) -> None:
    """Prüft rekursiv ohne Datenänderungen; meldet leere Blätter direkt über warn."""
    # Zuerst sicherstellen, dass die Unteraufgabe ein JSON-Objekt ist.
    if not isinstance(subtask, dict):
        raise ValueError(f"{location} ist kein JSON-Objekt.")
    # Optionale Kennzeichnungen und Punktwerte melden, ohne sie umzuschreiben.
    _validate_optional_subtask_metadata(subtask, location, warn=warn)
    validate_points(subtask, location, warn=warn)
    _validate_points_policy(subtask, location, allow_points=allow_points, warn=warn)
    # Fehlende Kinder oder null nur beim Lesen als leere Liste behandeln.
    children = child_nodes(subtask, location)
    # Alle Kinder rekursiv mit derselben Punkteregel und genauerer Ortsangabe prüfen.
    for index, child in enumerate(children, start=1):
        validate_subtask(
            child,
            location=f"{location}.{index}",
            allow_points=allow_points,
            warn=warn,
        )
    # Leerraum nur für die Inhaltsprüfung entfernen; den Originaltext nicht überschreiben.
    markdown = _optional_text(
        subtask.get("markdown"),
        f"{location}.markdown",
        warn=warn,
    ).strip()
    # Ein leeres Blatt nur melden und anschließend mit den übrigen Aufgaben fortfahren.
    if not markdown and not children and warn is not None:
        warn(f"WARNUNG: {location} enthaelt keinen Inhalt.")


def _validate_optional_subtask_metadata(
    subtask: dict[str, Any],
    location: str,
    *,
    warn: Callable[[str], None] | None = None,
) -> None:
    """Meldet falsche Typen in optional ausgewerteten Unteraufgabenfeldern."""
    for field in ("id", "title", "source_label"):
        _optional_text(
            subtask.get(field), f"{location}.{field}", warn=warn
        )


def _optional_text(
    value: Any,
    location: str,
    *,
    warn: Callable[[str], None] | None,
) -> str:
    """Liest optionalen Text und meldet andere Typen, ohne Quelldaten zu ändern."""
    if value is not None and not isinstance(value, str) and warn is not None:
        warn(
            f"WARNUNG: {location} ist weder Text noch null; "
            f"Wert bleibt {value!r} und wird beim Lesen als leer behandelt."
        )
    return text_or_empty(value)


def _validate_points_policy(
    item: dict[str, Any],
    location: str,
    *,
    allow_points: bool,
    warn: Callable[[str], None] | None = None,
) -> None:
    """Meldet Zahlenwerte im Feld ``points`` von Lösungen direkt über warn.

    Beispiel: points=3 erzeugt bei reference_solution/student_solution eine
    Warnung, bei assignment nicht. None (JSON-null) erzeugt keine Warnung.
    Der Wert bleibt erhalten; ohne warn erfolgt keine Ausgabe. Ob der Wert eine
    brauchbare Zahl ist, prüft ``validate_points`` separat.
    """
    if not allow_points and item.get("points") is not None and warn is not None:
        warn(
            f"WARNUNG: {location}.points ist {item.get('points')!r}; "
            "fuer diesen Dokumenttyp wird null erwartet."
        )


def validate_points(
    item: dict[str, Any],
    location: str,
    *,
    warn: Callable[[str], None] | None = None,
) -> None:
    """Meldet fehlende oder unbrauchbare Punkte, ohne den Wert zu verändern."""
    if "points" not in item:
        if warn is not None:
            warn(f"WARNUNG: {location} enthaelt kein points-Feld.")
        return
    try:
        parse_optional_positive_points(
            item["points"],
            location=f"{location}.points",
        )
    except ValueError as exc:
        if warn is not None:
            warn(f"WARNUNG: {exc} Wert bleibt {item['points']!r}.")
