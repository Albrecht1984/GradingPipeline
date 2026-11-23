"""Überführt extrahierte Aufgaben in hierarchisch partitionierte Hauptaufgaben.

Die Quelle ist das JSON der vorherigen Aufgabenextraktion im Dokumentordner.
Jede darin enthaltene Hauptaufgabe erhält einen eigenen Modellinput; das Modell
liefert den vollständigen Unteraufgabenbaum dieser Hauptaufgabe zurück. Die Pipeline
ruft das Modell also nicht erneut für jeden Knoten dieses Baums auf.

``extract()`` steuert Vorbereitung, Hauptaufgabenverarbeitung und Gesamtexport.
Pro Hauptaufgabe folgen Cache-Prüfung oder ein Modellaufruf,
abschließende Validierung und Speicherung. Die Dataclasses halten dafür
Pfade und Laufdaten auseinander. Die freien Funktionen am
Modulende parsen die Quelle, rendern Modellinput beziehungsweise Markdown
und erzeugen eine konfigurierte Pipeline.

Erfolgreiche Hauptaufgaben werden sofort im Cache vermerkt. Ein struktureller
Fehler bricht dennoch den gesamten Lauf ab; Gesamtausgaben werden erst nach
erfolgreicher Verarbeitung aller Hauptaufgaben geschrieben.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Any, Callable

from grading_pipeline.infrastructure.artifact_names import (
    TASK_EXTRACTION_ARTIFACTS,
    TASK_PARTITIONING_ARTIFACTS,
)
from grading_pipeline.infrastructure.model_calls import invoke_json_model
from grading_pipeline.models.metadata import model_identity
from grading_pipeline.models.responses import response_artifact, response_text
from grading_pipeline.models.json import parse_model_json_object
from grading_pipeline.infrastructure.hashing import sha256_text
from grading_pipeline.infrastructure.json_io import read_cache_json_object, write_json
from grading_pipeline.infrastructure.task_nodes import child_nodes, node_label, node_text
from grading_pipeline.caching.task_partitioning import (
    load_partitioned_task,
    partition_cache_model,
    partition_cache_records,
)
from grading_pipeline.caching.common import write_cache_document
from .artifacts import (
    render_heading,
    task_filename,
    write_task_markdown_artifacts,
)
from .base import TaskModelPipelineBase, TaskPartitioningResult
from grading_pipeline.infrastructure.statistics import (
    write_model_call_statistics,
)
from grading_pipeline.validation import validate_partitioned_tasks, validate_tasks


@dataclass(frozen=True)
class PartitioningPaths:
    """Bündelt die Ausgabeziele eines Dokumentlaufs, ohne sie anzulegen.

    Attributes:
        raw: Zusammengeführtes JSON aller partitionierten Hauptaufgaben.
        cache: Eingabeidentität und Pfade der bereits fertigen Hauptaufgaben.
        input: Zusammenstellung aller gerenderten Einzeleingaben zur Kontrolle.
        responses: Ordner für Modellantworten und Einzelnachweise.
        tasks: Ordner für die Markdown-Dateien der einzelnen Aufgaben.
        export: Gemeinsamer Markdown-Export des Dokuments.
    """

    raw: Path
    reviewed: Path
    cache: Path
    input: Path
    responses: Path
    tasks: Path
    export: Path


@dataclass(frozen=True)
class PartitionTaskArtifacts:
    """Beschreibt die festen Dateinamen einer Hauptaufgabe im Antwortordner.

    Attributes:
        response: Vollständige serialisierte LangChain-Antwort.
        raw: JSON der geprüften Partition.
        statistics: Statistiken des Modellaufrufs.
    """

    response: Path
    raw: Path
    statistics: Path


@dataclass(frozen=True)
class PartitioningSource:
    """Hält validierte Hauptaufgaben und daraus erzeugte Modellinputs.

    Attributes:
        path: Pfad zum JSON der vorausgehenden Aufgabenextraktion.
        document_title: Unverändert übernommener Dokumenttitel, gegebenenfalls ``None``.
        document_type: Validierter Dokumenttyp der Quelle.
        tasks: Validierte, unveränderte Quellaufgaben.
        task_inputs: Gerenderter Input je Aufgabe, in derselben Reihenfolge wie ``tasks``.
    """

    path: Path
    document_title: Any
    document_type: str
    tasks: list[dict[str, Any]]
    task_inputs: list[str]


@dataclass(frozen=True)
class PartitioningRunSetup:
    """Hält den Kontext, den alle Hauptaufgaben eines Laufs gemeinsam benötigen.

    ``frozen=True`` verhindert nur die Neuzuweisung von Feldern; die enthaltenen
    Listen und Dictionaries sind dadurch nicht tiefgehend unveränderlich.

    Attributes:
        document_dir: Absolut aufgelöster Dokumentordner.
        source: Geladene Quelle mit Dokumentdaten und gerenderten Einzeleingaben.
        paths: Ziele der Gesamtartefakte und Ausgabeordner.
        cache_identity: Modellidentität dieses Laufs.
        old_records: Passende Cache-Einträge, indiziert nach Index und Input-Hash.
    """

    document_dir: Path
    source: PartitioningSource
    paths: PartitioningPaths
    cache_identity: dict[str, Any]
    old_records: dict[tuple[int, str], dict[str, Any]]


@dataclass(frozen=True)
class PartitionedTaskOutcome:
    """Gibt die drei Beiträge einer erfolgreich abgeschlossenen Hauptaufgabe zurück.

    Attributes:
        task: Validierte Partition für das zusammengeführte Ergebnis.
        record: Minimale Eingabeidentität für den nächsten Cache-Zwischenstand.
        from_cache: Ob das Ergebnis ohne Modellaufruf geladen wurde.
    """

    task: dict[str, Any]
    record: dict[str, Any]
    from_cache: bool


class TaskPartitioningPipeline(TaskModelPipelineBase):
    """Partitioniert pro Hauptaufgabe einmalig; Inhaltsabweichungen werden nur gemeldet."""

    source_filename = TASK_PARTITIONING_ARTIFACTS.source
    reviewed_source_filename = TASK_EXTRACTION_ARTIFACTS.reviewed_json
    source_label = "JSON der vollstaendigen Aufgabenextraktion"
    tasks_dirname = TASK_PARTITIONING_ARTIFACTS.tasks_dir
    export_filename = TASK_PARTITIONING_ARTIFACTS.export_markdown
    operation = "Aufgabenpartitionierung"
    input_artifact_filename = TASK_PARTITIONING_ARTIFACTS.input_markdown
    response_dirname = TASK_PARTITIONING_ARTIFACTS.responses_dir

    def extract(
        self,
        document_dir: Path,
        *,
        output_dir: Path | None = None,
        overwrite: bool = False,
        use_cache: bool = False,
    ) -> TaskPartitioningResult:
        """Partitioniert alle Quellaufgaben und schreibt Einzel- und Gesamtausgaben.

        Für jede Hauptaufgabe wird ein passender Cache-Kandidat verwendet oder ein
        Modellaufruf ausgeführt. Nach jeder erfolgreichen Hauptaufgabe wird der
        bisherige Cache vollständig geschrieben.
        Erst nach der letzten Hauptaufgabe entstehen Gesamt-JSON und Markdown-Exporte.
        Ein Fehler stoppt den Lauf; frühere Einzelnachweise bleiben
        erhalten und können bei einem späteren Cache-Lauf wiederverwendet werden.

        Args:
            document_dir: Ordner mit dem JSON der vorausgehenden Aufgabenextraktion.
            output_dir: Optionaler separater Ausgabeordner. Ohne Angabe wird
                ``document_dir`` auch als Ausgabeordner verwendet.
            overwrite: Entfernt vorhandene Partitionsausgaben einschließlich des
                Antwortordners. Eine dadurch gelöschte Antwort ist kein Cache-Treffer.
            use_cache: Liest vorhandene Cache-Metadaten und prüft die Einzelnachweise.
                Auch Cache-Läufe erstellen Gesamtartefakte und Markdown erneut.
                Ohne beide Optionen sind vorhandene Partitionsausgaben ein Fehler.

        Returns:
            Ergebnis mit Exportpfaden und Anzahl der obersten Hauptaufgaben, nicht der
            Unteraufgaben. ``from_cache`` ist nur bei einer nicht leeren, vollständig
            ohne neue Modellversuche verarbeiteten Quelle wahr.

        Raises:
            FileNotFoundError: Wenn die Quelldatei fehlt.
            FileExistsError: Wenn vorhandene Ausgaben weder ersetzt noch als Cache
                berücksichtigt werden dürfen.
            ValueError: Bei ungültiger Quelle oder nicht akzeptierbarer Endpartition.
            OSError: Wenn das Lesen, Schreiben oder Entfernen von Artefakten scheitert.

        Note:
            Providerfehler werden nicht abgefangen und brechen den Lauf ebenfalls ab.
        """
        run = self._prepare_partitioning_run(
            document_dir=document_dir,
            output_dir=output_dir,
            overwrite=overwrite,
            use_cache=use_cache,
        )
        cache_metadata_path = run.paths.cache
        cache_identity = run.cache_identity
        new_records: list[dict[str, Any]] = []
        partitioned_tasks: list[dict[str, Any]] = []
        cache_hits: list[bool] = []

        for index, (source_task, task_input) in enumerate(
            zip(run.source.tasks, run.source.task_inputs), start=1
        ):
            outcome = self._partition_task(
                run=run,
                index=index,
                source_task=source_task,
                task_input=task_input,
            )
            partitioned_tasks.append(outcome.task)
            new_records.append(outcome.record)
            cache_hits.append(outcome.from_cache)
            write_cache_document(
                cache_metadata_path,
                metadata={"model": cache_identity, "tasks": new_records},
            )

        return self._finalize_partitioning_run(
            run=run,
            partitioned_tasks=partitioned_tasks,
            cache_hits=cache_hits,
        )

    def _finalize_partitioning_run(
        self,
        *,
        run: PartitioningRunSetup,
        partitioned_tasks: list[dict[str, Any]],
        cache_hits: list[bool],
    ) -> TaskPartitioningResult:
        """Schließt einen vollständig erfolgreichen Lauf ab.

        Schreibt Gesamt-JSON und rendert anschließend Markdown. Schreibfehler werden
        weitergereicht; bereits erzeugte Dateien werden nicht zurückgerollt.

        Args:
            run: Gemeinsame Quelldaten und Ausgabeziele.
            partitioned_tasks: Akzeptierte Hauptaufgaben in Quellreihenfolge.
            cache_hits: Cache-Status der Hauptaufgaben in derselben Reihenfolge.

        Returns:
            Öffentliches Ergebnis; ``from_cache`` ist nur für einen nicht leeren Lauf
            wahr, dessen Hauptaufgaben ausschließlich Cache-Treffer waren.
        """
        self._write_aggregate_partition_artifacts(
            run=run,
            partitioned_tasks=partitioned_tasks,
        )
        write_task_markdown_artifacts(
            partitioned_tasks,
            tasks_dir=run.paths.tasks,
            export_path=run.paths.export,
            render=render_partitioned_task,
        )
        self.progress(f"Aufgabenexport gespeichert: {run.paths.export}")
        self.progress("Aufgabenpartitionierung abgeschlossen.")
        return TaskPartitioningResult(
            document_dir=run.document_dir,
            combined_markdown_path=run.paths.export,
            extraction_json_path=run.paths.raw,
            task_count=len(partitioned_tasks),
            from_cache=bool(cache_hits) and all(cache_hits),
        )

    @staticmethod
    def _write_aggregate_partition_artifacts(
        *,
        run: PartitioningRunSetup,
        partitioned_tasks: list[dict[str, Any]],
    ) -> None:
        """Schreibt die zusammengeführte Partition als JSON-Datei.

        ``run`` liefert Titel, Dokumenttyp und Zielpfade. ``partitioned_tasks`` wird
        unter ``tasks`` im Gesamt-JSON gespeichert. Die Methode validiert die
        übergebenen Ergebnisse nicht erneut und aktualisiert nicht den Cache.
        """
        write_json(
            run.paths.raw,
            {
                "document_title": run.source.document_title,
                "document_type": run.source.document_type,
                "tasks": partitioned_tasks,
            },
        )

    def _partition_task(
        self,
        *,
        run: PartitioningRunSetup,
        index: int,
        source_task: dict[str, Any],
        task_input: str,
    ) -> PartitionedTaskOutcome:
        """Verwendet einen gültigen Cache oder eine Modellantwort pro Hauptaufgabe."""
        stem = task_filename(
            index, node_label(source_task, f"task_{index:03d}")
        ).removesuffix(".md")
        artifacts = PartitionTaskArtifacts(
            response=run.paths.responses / f"{stem}.response.json",
            raw=run.paths.responses / f"{stem}.raw.json",
            statistics=run.paths.responses / f"{stem}.statistics.json",
        )
        prompt = self.prompt_template.format(content=task_input)
        input_sha256 = sha256_text(prompt)
        record = run.old_records.get((index, input_sha256))
        response_path = artifacts.response
        task = load_partitioned_task(
            record=record,
            raw_json_path=artifacts.raw,
            validator=lambda data: validate_partitioned_tasks(
                data, expected_document_type=run.source.document_type,
            ),
        )
        from_cache = task is not None
        if from_cache:
            self.progress(f"Hauptaufgabe {index}/{len(run.source.tasks)} aus Cache: {source_task.get('id')}")
        else:
            total = len(run.source.tasks)
            response, started_at = invoke_json_model(
                self.model,
                prompt,
                progress=self.progress,
                heartbeat_label=(
                    f"Aufgabenpartitionierung {index}/{total} beim Modell"
                ),
                result_label=f"Aufgabe {index}/{total}",
            )
            write_json(response_path, response_artifact(response))
            write_model_call_statistics(
                artifacts.statistics,
                model=self.model,
                response=response,
                stage="task_partitioning",
                model_input=prompt,
                started_at=started_at,
                warn=self.warn,
            )
            task = self._assess_partition_response(
                response_text(response), document_type=run.source.document_type,
                index=index,
            )
            write_json(artifacts.raw, {
                "document_title": run.source.document_title,
                "document_type": run.source.document_type,
                "tasks": [task],
            })
        record = {"index": index, "input_sha256": input_sha256}
        return PartitionedTaskOutcome(
            task=task, record=record, from_cache=from_cache,
        )

    def _prepare_partitioning_run(
        self,
        *,
        document_dir: Path,
        output_dir: Path | None,
        overwrite: bool,
        use_cache: bool,
    ) -> PartitioningRunSetup:
        """Lädt die Quelle und bereitet alle gemeinsam verwendeten Laufdaten vor.

        Der Dokumentordner wird absolut aufgelöst. Bei ``use_cache`` werden alte
        Cache-Metadaten vor der Ausgabebereinigung gelesen. Danach wird das gemeinsame
        Kontrollartefakt aus den Einzeleingaben geschrieben und der Antwortordner
        angelegt. Nur zur aktuellen Modellidentität passende Cache-Datensätze werden
        in den zurückgegebenen Kontext übernommen; der fertige Prompt wird je Aufgabe
        separat gehasht.

        Args:
            document_dir: Quellordner der vollständigen Aufgabenextraktion.
            output_dir: Optionaler separater Zielordner der Partitionierung.
            overwrite: Entfernt auch vorhandene Antwortartefakte.
            use_cache: Erlaubt das Lesen alter Cache-Metadaten; ohne ``overwrite``
                bleiben die Einzelnachweise für die spätere Trefferprüfung erhalten.

        Returns:
            Vorbereiteter Kontext mit parallel angeordneten Quellaufgaben und Inputs.

        Raises:
            FileNotFoundError: Wenn die Aufgabenquelle fehlt.
            FileExistsError: Wenn Ausgaben ohne Ersetzungs- oder Cache-Erlaubnis existieren.
            ValueError: Wenn die Quelle leer oder strukturell ungültig ist.
        """
        document_dir = document_dir.resolve()
        source = self._load_partitioning_source(document_dir)
        resolved_output_dir = (
            output_dir.resolve() if output_dir is not None else document_dir
        )
        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        paths = self._partitioning_paths(resolved_output_dir)
        old_cache = read_cache_json_object(paths.cache) if use_cache else None
        self._prepare_partitioning_outputs(
            paths=paths,
            overwrite=overwrite,
            use_cache=use_cache,
        )
        self._write_input_artifact(paths.input, "\n\n---\n\n".join(source.task_inputs))
        paths.responses.mkdir(parents=True, exist_ok=True)
        cache_identity = partition_cache_model(model_identity(self.model, json_mode=True))
        return PartitioningRunSetup(
            document_dir=resolved_output_dir,
            source=source,
            paths=paths,
            cache_identity=cache_identity,
            old_records=partition_cache_records(old_cache, cache_identity),
        )

    def _load_partitioning_source(
        self,
        document_dir: Path,
    ) -> PartitioningSource:
        """Liest und validiert die Aufgabenquelle und rendert pro Hauptaufgabe einen Input.

        Gesucht wird ``self.source_filename`` innerhalb von ``document_dir``.
        Die Validierung verändert das geparste Dictionary nicht; die
        Quelldatei selbst bleibt unverändert. Der zurückgegebene Quelltext ist der
        gelesene, außen bereinigte Text und nicht eine erneute JSON-Serialisierung.

        Returns:
            Quelle mit Dokumentmetadaten, validierten Hauptaufgaben und je einem
            zugehörigen Modellinput in Quellreihenfolge. Es werden keine Dateien geschrieben.

        Raises:
            FileNotFoundError: Wenn die konfigurierte Quelldatei nicht existiert.
            ValueError: Wenn sie leer ist, kein JSON-Objekt enthält oder die
                Aufgabenstruktur beziehungsweise der Dokumenttyp ungültig ist.
        """
        source_path, source_content = self._load_source_text(document_dir)

        source_data = parse_extracted_tasks_json(source_content)
        validate_tasks(source_data)
        source_tasks = source_data["tasks"]
        document_title = source_data.get("document_title")
        document_type = source_data["document_type"]
        task_inputs = [
            render_partitioning_task_input(
                document_title=document_title,
                document_type=document_type,
                task=task,
                index=index,
                total=len(source_tasks),
            )
            for index, task in enumerate(source_tasks, start=1)
        ]
        return PartitioningSource(
            path=source_path,
            document_title=document_title,
            document_type=document_type,
            tasks=source_tasks,
            task_inputs=task_inputs,
        )

    def _partitioning_paths(self, document_dir: Path) -> PartitioningPaths:
        """Verknüpft ``document_dir`` mit den zentral definierten Artefaktnamen.

        Liefert einen ``PartitioningPaths``-Container, ohne Pfade aufzulösen,
        Dateien zu prüfen oder Verzeichnisse anzulegen. Der Aufrufer übergibt
        im normalen Lauf bereits den absolut aufgelösten Dokumentordner.
        """
        return PartitioningPaths(
            raw=document_dir / TASK_PARTITIONING_ARTIFACTS.raw_json,
            reviewed=document_dir / TASK_PARTITIONING_ARTIFACTS.reviewed_json,
            cache=document_dir / TASK_PARTITIONING_ARTIFACTS.cache_json,
            input=document_dir / self.input_artifact_filename,
            responses=document_dir / self.response_dirname,
            tasks=document_dir / self.tasks_dirname,
            export=document_dir / self.export_filename,
        )

    def _prepare_partitioning_outputs(
        self,
        *,
        paths: PartitioningPaths,
        overwrite: bool,
        use_cache: bool,
    ) -> None:
        """Prüft Ausgabekonflikte und entfernt vorhandene Partitionsartefakte.

        ``paths`` bestimmt die betroffenen Gesamtdateien, den Aufgabenordner und
        den Antwortordner. Ohne ``overwrite`` und ``use_cache`` genügt ein einziges
        vorhandenes Ziel für einen Fehler. Mit ``overwrite`` werden Gesamtdateien,
        Aufgabenordner und Antwortordner entfernt. Bei ausschließlich ``use_cache``
        bleiben die Einzelnachweise im Antwortordner erhalten, während Gesamtdateien
        einschließlich Cache-Datei und Aufgabenordner gelöscht werden.

        Deshalb muss der Aufrufer Cache-Metadaten vor diesem Schritt einlesen.
        Die Quelldatei gehört nicht zu den bereinigten Zielen.

        Raises:
            FileExistsError: Wenn vorhandene Ausgaben nicht bearbeitet werden dürfen.
            OSError: Wenn eine Datei oder ein Ausgabeordner nicht entfernt werden kann.
        """
        aggregate_paths = [
            paths.raw,
            paths.cache,
            paths.input,
            paths.export,
        ]
        if not overwrite and not use_cache:
            existing = [path for path in aggregate_paths if path.exists()]
            existing.extend(
                path
                for path in (paths.responses, paths.tasks)
                if path.exists()
            )
            if existing:
                raise FileExistsError(
                    "Ergebnisse der Aufgabenpartitionierung existieren bereits. "
                    "Nutze --overwrite zum Ersetzen."
                )
        if overwrite:
            self._prepare_outputs(aggregate_paths, paths.tasks, overwrite=True)
            paths.reviewed.unlink(missing_ok=True)
            if paths.responses.is_dir():
                shutil.rmtree(paths.responses)
        elif use_cache:
            self._prepare_outputs(aggregate_paths, paths.tasks, overwrite=True)

    def _assess_partition_response(
        self,
        content: str,
        *,
        document_type: str,
        index: int,
    ) -> dict[str, Any]:
        """Prüft das Format direkt; meldet Inhalts- und Metadatenabweichungen ohne Änderung."""
        data = parse_model_json_object(
            content, response_label="LLM-Antwort",
        )
        validate_partitioned_tasks(data, expected_document_type=document_type)
        if len(data["tasks"]) != 1:
            raise ValueError(f"Hauptaufgabe {index}: Das Modell muss genau eine Hauptaufgabe ausgeben.")
        task = data["tasks"][0]
        return task

def parse_extracted_tasks_json(source_json: str) -> dict[str, Any]:
    """Liest ``source_json`` mit dem Standard-JSON-Parser als Dictionary ein.

    Anders als beim Parsing von Modellantworten werden weder Markdown-Zäune
    entfernt noch eingebettete Objekte gesucht. Die Funktion prüft nur die
    JSON-Syntax und den obersten Typ; fachliche Felder validiert der Aufrufer.

    Returns:
        Neu geparstes JSON-Objekt ohne Prüfung seines Aufgabenschemas.

    Raises:
        ValueError: Bei ungültiger JSON-Syntax oder einem anderen obersten JSON-Typ.
            Syntaxfehler werden als Ursache der verständlicheren Meldung erhalten.
    """
    try:
        data = json.loads(source_json)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Das JSON der Aufgabenextraktion ist ungueltig: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError("Das JSON der Aufgabenextraktion ist kein JSON-Objekt.")
    return data

def render_partitioning_task_input(
    *,
    document_title: Any,
    document_type: str,
    task: dict[str, Any],
    index: int,
    total: int,
) -> str:
    """Rahmt genau eine Quellaufgabe als eigenständig verständlichen Modellinput ein.

    Dokument- und Aufgabenmetadaten werden als JSON-Werte geschrieben, damit etwa
    ``None`` und Sonderzeichen eindeutig dargestellt sind. Der Markdown-Inhalt
    wird von einer redundanten Aufgabenüberschrift bereinigt und zwischen festen
    Markern eingefügt. Der Input enthält weder andere Aufgaben noch die Promptvorlage.

    Args:
        document_title: Dokumenttitel als JSON-serialisierbarer Wert.
        document_type: Bereits validierter Dokumenttyp.
        task: Validierte Quellaufgabe mit ``markdown`` und ihren Metadaten.
        index: Einsbasierte Position der Hauptaufgabe.
        total: Gesamtzahl der Quellaufgaben.

    Returns:
        Gerahmter Text zum Einsetzen in den Platzhalter ``{{ content }}``.
        Das übergebene Aufgaben-Dictionary wird nicht verändert.

    Raises:
        TypeError: Wenn ein Metadatenwert nicht JSON-serialisierbar ist.
    """
    task_id = json.dumps(task.get("id"), ensure_ascii=False)
    source_label = json.dumps(task.get("source_label"), ensure_ascii=False)
    title = json.dumps(task.get("title"), ensure_ascii=False)
    points = json.dumps(task.get("points"), ensure_ascii=False)
    markdown = node_text(task, "markdown").strip()
    return "\n".join(
        (
            "# Eingabe fuer die Hauptaufgabenpartitionierung",
            f"DOKUMENTTITEL_JSON: {json.dumps(document_title, ensure_ascii=False)}",
            f"DOKUMENTTYP_JSON: {json.dumps(document_type, ensure_ascii=False)}",
            f"EINHEIT_INDEX: {index} VON {total}",
            "<<< EINHEIT BEGINN >>>",
            f"ID_JSON: {task_id}",
            f"SOURCE_LABEL_JSON: {source_label}",
            f"TITEL_JSON: {title}",
            f"PUNKTE_JSON: {points}",
            "MARKDOWN_BEGINN",
            markdown,
            "MARKDOWN_ENDE",
            "<<< EINHEIT ENDE >>>",
        )
    )

def render_partitioned_task(task: dict[str, Any]) -> str:
    """Rendert eine validierte oberste Hauptaufgabe einschließlich aller Unteraufgaben.

    Args:
        task: Partitionierte Aufgabe mit ``points`` sowie optionalem Titel,
            Einleitungstext, Unteraufgaben und Schlusstext.

    Returns:
        Markdown mit einer Überschrift auf Ebene zwei, anschließend Einleitung,
        rekursiv gerenderten Unteraufgaben und Schlusstext. Äußere Leerzeichen
        werden entfernt; es wird keine Datei geschrieben und ``task`` nicht verändert.

    """
    task_id = node_label(task, "Aufgabe")
    parts = [render_heading(task_id, task.get("title"), task.get("points"), level=2)]
    introduction = node_text(task, "introduction_markdown").strip()
    if introduction:
        parts.append(introduction)
    for subtask in child_nodes(task, "Hauptaufgabe"):
        parts.extend(render_subtask(subtask, depth=1))
    closing = node_text(task, "closing_markdown").strip()
    if closing:
        parts.append(closing)
    return "\n\n".join(parts).strip()

def render_subtask(subtask: dict[str, Any], depth: int) -> list[str]:
    """Sammelt Markdown-Blöcke einer Unteraufgabe in Tiefensuchreihenfolge.

    Args:
        subtask: Validierter Knoten mit ``points``, optionalem Markdown und Kindern.
        depth: Tiefe relativ zur obersten Aufgabe; direkte Kinder beginnen bei eins.

    Returns:
        Flache Liste aus Überschrift, eigenem Inhalt und Blöcken aller Nachkommen.
        Die Überschrift verwendet ``min(2 + depth, 6)``; die Rekursion läuft auch
        jenseits der sechsten Überschriftenebene weiter. Eingabeknoten bleiben unverändert.

    """
    heading_level = min(2 + depth, 6)
    subtask_id = node_label(subtask, "Teil")
    parts = [
        render_heading(
            subtask_id,
            subtask.get("title"),
            subtask.get("points"),
            level=heading_level,
        )
    ]
    markdown = node_text(subtask, "markdown").strip()
    if markdown:
        parts.append(markdown)
    for child in child_nodes(subtask, subtask_id):
        parts.extend(render_subtask(child, depth=depth + 1))
    return parts
