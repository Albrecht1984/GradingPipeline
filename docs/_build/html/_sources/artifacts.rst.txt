Artefakte und Wiederanlauf
==========================

Ergebnis- und Begleitartefakte
------------------------------

Die Stufen speichern ihre Ergebnisse als Markdown, JSON und gegebenenfalls
Bilder. Die folgende Tabelle zeigt die Übergaben und die Dateinamen für
geprüfte Fassungen. Die nächste Stufe verwendet eine vorhandene
``.reviewed``-Datei bevorzugt.

.. list-table::
   :header-rows: 1
   :widths: 26 37 37

   * - Stufe
     - Ergebnis für die Weiterverarbeitung
     - Name für manuelle Korrekturen
   * - Visuelle Extraktion
     - ``03_vlm_export.raw.md``
     - ``03_vlm_export.reviewed.md``
   * - Aufgabenextraktion
     - ``04_task_extraction.raw.json``
     - ``04_task_extraction.reviewed.json``
   * - Aufgabenpartitionierung
     - ``06_task_partitioning.raw.json``
     - ``06_task_partitioning.reviewed.json``
   * - Rubric-Erzeugung
     - ``02_rubrics.raw.json``
     - ``02_rubrics.reviewed.json``
   * - Bewertung
     - ``03_grading_results.raw.json``
     - —

Die Bewertung schreibt zusätzlich den Strukturbericht
``01_structure_check.json`` sowie die beiden Markdown-Berichte
``04_grading_report.md`` und ``05_student_feedback.md``.

Bei der Dokumentaufbereitung entstehen außerdem Verzeichnisse wie
``01_pages/`` für gerenderte Seiten, ``02_page_responses/`` für
seitenweise Modellantworten, ``05_tasks/`` für extrahierte Aufgaben
und ``07_partitioned_tasks/`` für partitionierte Aufgaben.

Weitere technische Begleitdateien sind ``*.response.json`` für
gespeicherte Modellantworten, ``*.cache.json`` für Informationen
zur Wiederverwendung vorhandener Ergebnisse und
``*.statistics.json`` für Aufrufstatistiken.
Nicht jeder Verarbeitungsschritt erzeugt sämtliche Artefakttypen.
Bei abgebrochenen Modellaufrufen können insbesondere Antwort- und
Statistikdateien fehlen.

Die exakten Dateinamen je Stufe stehen in
:doc:`api/developer/artifacts_cache`.

Ein regulärer Lauf lässt die geprüfte Fassung bestehen. Vor
``--overwrite true`` die manuell gepflegten Dateien sichern. Je nach Stufe
kann der Befehl auch die geprüfte Fassung des neu erzeugten Ergebnisses
entfernen. Raw- und Reviewed-Fassungen lassen sich unabhängig bearbeiten.

Aufgabenbaum und Bewertung
--------------------------

Ein partitioniertes Dokument enthält ``document_type``,
``document_title`` und ``tasks``. Die Knoten enthalten unter anderem
``id``, ``source_label``, ``title``, ``points``,
``introduction_markdown``, ``markdown`` und ``subtasks``.
Die Positionen im Baum bestimmen strukturelle Pfade wie
``tasks[0].subtasks[0]``. Die Pipeline richtet anhand dieser Pfade
Aufgabenstellung, studentische Lösung und optionale Musterlösung aus.

Der Validator gibt seine Befunde auf der Konsole aus. Blockierende Befunde
führen zu Exitcode 1. Reine Qualitätshinweise ergeben Exitcode 0.
Die fachliche Richtigkeit von Transkription und Bewertung erfordert eine
inhaltliche Prüfung. Fehlgeschlagene Bewertungsziele können zu einem Ergebnis
mit ``status: incomplete`` führen. Fehlende Bewertungen zählen dabei
nicht als null Punkte.

Cache und Aufrufstatistik
-------------------------

Ein Cache-Treffer setzt passende Eingaben und Modellkonfiguration voraus.
Die Granularität folgt dem Modellaufruf, etwa pro Seite bei der visuellen
Extraktion und pro Blatt bei der Bewertung. Existierende Rohantworten werden
bei einem Treffer erneut eingelesen. Mit ``--overwrite true`` kann man
für eine Stufe neue Modellantworten anfordern.

Bei neuen Modellaufrufen entstehen ``*.statistics.json`` mit Laufzeit,
Modellkonfiguration und verfügbaren Providerdaten wie Tokenzahlen. Die
Felder und internen Cache-Schnittstellen beschreibt die
:doc:`api/developer/artifacts_cache`.

Bildsupplemente
---------------

Bei der visuellen Extraktion markierte BBOX-Bereiche werden aus den
gerenderten Seiten ausgeschnitten. Nach einer Korrektur der Markierungen
in ``03_vlm_export.reviewed.md`` kann ``prepare-images`` die Ausschnitte
modellfrei aktualisieren.

Für ``grade-with-images`` im passenden Knoten des geprüften Aufgabenbaums
``06_task_partitioning.reviewed.json`` das Feld
``image_supplement_refs`` ergänzen. Es enthält eine Liste von Bild-IDs aus
``03_image_supplements/manifest.json`` desselben Dokumentordners. Eine
Zuordnung an einem Elternknoten gilt auch für seine Blattknoten. Nur
referenzierte Ausschnitte gelangen in den multimodalen Modellinput.
