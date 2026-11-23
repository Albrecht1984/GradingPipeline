JSON-Datenformate
=================

Diese Seite erläutert die drei wichtigsten JSON-Formate der Pipeline:
Aufgabenbäume, Rubrics und Bewertungsergebnisse. Die Beispiele zeigen
kleine, zusammenpassende Datensätze und sind keine vollständige formale
JSON-Schema-Definition. Feldnamen und Verschachtelung entsprechen der
Implementierung.

Die zugehörigen Dateinamen beschreibt :doc:`artifacts`. Die folgenden
Erläuterungen helfen insbesondere beim Prüfen und manuellen Bearbeiten
gespeicherter Ergebnisse.

Manuelle Bearbeitung und Validierung
------------------------------------

Für Aufgabenextraktion, Aufgabenpartitionierung und Rubric-Erzeugung können
manuell geprüfte Fassungen hinterlegt werden. Dafür die entsprechende
``.raw.json`` im selben Verzeichnis als ``.reviewed.json`` kopieren und
anschließend die Kopie bearbeiten. Die Pipeline bevorzugt vorhandene
geprüfte Fassungen bei der Weiterverarbeitung.

Die überarbeitete Datei lässt sich ohne Modellaufruf prüfen::

   python main.py validate --input PFAD_ZUM_ORDNER

``PFAD_ZUM_ORDNER`` bezeichnet den Ordner mit den Artefakten, nicht den
Pfad zu einer einzelnen JSON-Datei. Vor Änderungen empfiehlt sich eine
Sicherung. Bei Aufgabenbäumen müssen die Dokumentrollen und die
strukturelle Zuordnung der Blattaufgaben zueinander passen.

``03_grading_results.raw.json`` ist dagegen ein Bewertungsergebnis und
keine reguläre ``.reviewed``-Eingabe. Nach einer Korrektur der Eingaben
wird die Bewertung mit ``grade`` erneut ausgeführt. Ein ausführliches
Beispiel zur Wiederaufnahme steht im :doc:`workflow`.

Der Befehl ``validate`` meldet technische Fehler und Qualitätshinweise.
Blockierende Befunde ergeben Exitcode 1, reine Qualitätshinweise dagegen
Exitcode 0. Die Validierung ersetzt keine fachliche Prüfung und
garantiert nicht, dass jeder nachfolgende Verarbeitungsschritt erfolgreich
ist. Details zu Datenmodellen und Prüfungen stehen in
:doc:`api/developer/schemas` und :doc:`api/developer/validation`.

Aufgabenbäume
-------------

Die Dateien ``04_task_extraction.raw.json`` und
``06_task_partitioning.raw.json`` enthalten Aufgabenstrukturen. Bei der
Aufgabenextraktion steht jede Hauptaufgabe noch als zusammenhängender
Markdown-Text in ``markdown``. Nach der Partitionierung beschreibt
``subtasks`` die rekursive Gliederung bis zu den Blattaufgaben.

Das folgende Beispiel ist **gekürzt**: Es enthält nur Teilaufgabe a)
mit einem Punkt. Die mitgelieferte Beispieldatei enthält dagegen die
Teilaufgaben a) und b) mit insgesamt zwei Punkten. Der Ausschnitt
veranschaulicht das Format und darf nicht unverändert als Ersatz für
den vollständigen Aufgabenbaum verwendet werden.

Beispiel eines gekürzten partitionierten Aufgabenbaums:

.. code-block:: json

   {
     "document_type": "assignment",
     "document_title": "Aufgabenstellung",
     "tasks": [
       {
         "id": "1",
         "source_label": "Aufgabe 1",
         "title": "Ausleihe in der Bibliothek",
         "points": 1,
         "introduction_markdown": "Eine Bibliothek verleiht Bücher für drei Wochen.",
         "closing_markdown": null,
         "subtasks": [
           {
             "id": "a",
             "source_label": "a)",
             "title": null,
             "points": 1,
             "markdown": "Wie lange darf man ein Buch behalten?",
             "subtasks": []
           }
         ]
       }
     ]
   }

.. list-table:: Wichtige Felder
   :header-rows: 1
   :widths: 32 68

   * - Feld
     - Bedeutung
   * - ``document_type``
     - Dokumentrolle: ``assignment``, ``reference_solution`` oder
       ``student_solution``.
   * - ``document_title``
     - Titel des Dokuments, falls bekannt.
   * - ``tasks`` / ``subtasks``
     - Listen von Hauptaufgaben bzw. untergeordneten Aufgaben.
       ``subtasks: []`` kennzeichnet einen Blattknoten.
   * - ``id`` / ``source_label``
     - Kennung bzw. Bezeichnung aus dem Dokument; sie legen den
       strukturellen Pfad **nicht** fest.
   * - ``title``
     - Optionaler Titel eines Aufgabenknotens.
   * - ``points``
     - Punktvorgabe, sofern vorhanden; ``null`` insbesondere bei
       Musterlösungen und studentischen Bearbeitungen.
   * - ``markdown``
     - Inhalt eines Knotens, insbesondere einer Blattaufgabe.
   * - ``introduction_markdown`` / ``closing_markdown``
     - Einleitender bzw. abschließender Text eines übergeordneten Knotens.
   * - ``image_supplement_refs``
     - Optionale Liste von Bild-IDs für die multimodale Bewertung;
       siehe :doc:`artifacts`.

Die Zuordnung erfolgt **nach der Position im Baum**, nicht anhand von
``id`` oder ``source_label``. Im Beispiel besitzt die Teilaufgabe a)
den Pfad ``tasks[0].subtasks[0]``. Aufgabenstellung, Musterlösung und
studentische Bearbeitung müssen für die strukturierte Bewertung an den
entsprechenden Positionen zusammenpassen. Die strukturelle Prüfung
beweist keine fachliche Gleichwertigkeit ihrer Inhalte. Ein isoliert
gültiger JSON-Aufgabenbaum kann daher beim Grading zu einem Strukturfehler
führen, wenn die anderen Dokumentrollen anders gegliedert sind. Für reine
Textkorrekturen genügt es üblicherweise, ``markdown`` zu bearbeiten und
die Knotenreihenfolge unverändert zu lassen.

Das vollständige Beispiel mit allen drei Dokumentrollen liegt unter
``examples/kurzantwort/prepared/`` im Projektverzeichnis.

Rubrics
-------

Die Datei ``02_rubrics.raw.json`` enthält eine Liste von Rubrics.
Eine Rubric gehört jeweils zu **einer Blattaufgabe**, die durch
``target_path`` bezeichnet wird. Die Modellantwort für eine einzelne
Rubric enthält im Wesentlichen ``target_path``, ``max_points`` und
``criteria``; die Pipeline ergänzt beim Zusammenführen weitere
Metadaten und die äußere Dokumentstruktur.

Schematisches Beispiel eines vollständigen Rubric-Artefakts:

.. code-block:: json

   {
     "status": "complete",
     "assignment_document_title": "Aufgabenstellung",
     "reference_solution_document_title": "Musterlösung",
     "rubrics": [
       {
         "target_path": "tasks[0].subtasks[0]",
         "display_label": "Aufgabe 1 / a)",
         "assignment_id": "a",
         "assignment_source_label": "a)",
         "reference_solution_id": "a",
         "reference_solution_source_label": "a)",
         "title": null,
         "max_points": 1,
         "criteria": [
           {
             "id": "criterion_001",
             "description": "Leihfrist nennen",
             "points": 1,
             "full_credit": "Die Leihfrist von drei Wochen wird genannt.",
             "credit_items": [
               {
                 "id": "credit_001",
                 "points": 1,
                 "requirement": "Drei Wochen nennen."
               }
             ],
             "acceptable_alternatives": "Auch 21 Tage gelten als richtig."
           }
         ]
       }
     ]
   }

.. list-table:: Wichtige Felder
   :header-rows: 1
   :widths: 34 66

   * - Feld
     - Bedeutung
   * - ``rubrics``
     - Liste der zugeordneten Einzelrubrics.
   * - ``target_path``
     - Struktureller Pfad der zugehörigen Blattaufgabe.
   * - ``max_points``
     - Vorgesehene Maximalpunktzahl der Aufgabe, gegebenenfalls ``null``.
   * - ``criteria``
     - Liste von Bewertungskriterien.
   * - ``description`` / ``full_credit``
     - Bezeichnung eines Kriteriums bzw. Beschreibung der vollen Leistung.
   * - ``credit_items``
     - Einzeln bepunktbare Teilleistungen; jedes Item enthält
       ``id``, ``points`` und ``requirement``.
   * - ``acceptable_alternatives``
     - Optionaler Text mit fachlich gleichwertigen Alternativen oder
       ``null``. Diese Alternativen werden nicht zusätzlich bepunktet.
   * - ``status``
     - ``complete``, wenn alle Rubrics erzeugt wurden, sonst ``incomplete``.

Die Punktzahlen der ``credit_items`` sollen sich zu den Punkten des
jeweiligen Kriteriums und die Kriterienpunkte zur Aufgabenpunktzahl
addieren. Die Validierung meldet bestimmte Abweichungen als
**Qualitätshinweise**, statt die Modellwerte stillschweigend zu ändern.
Die bloße technische Lesbarkeit einer Rubric garantiert deshalb keine
fachlich richtige oder vollständige Bewertungsgrundlage.

Im Beispiel ist ``21 Tage`` lediglich eine alternative Formulierung der
bereits mit einem Punkt bewerteten Leistung ``drei Wochen`` – kein
zusätzliches ``credit_item``. Jeder ``target_path`` darf innerhalb der
Rubric-Liste höchstens einmal vorkommen. Doppelte Zielpfade erzeugen bei
``validate`` einen Qualitätshinweis; beim Grading führen sie dagegen
zu einem Abbruch. Ein Validierungslauf mit Exitcode 0 allein bestätigt
also nicht die Verwendbarkeit für die Bewertung.

Bewertungsergebnisse
--------------------

Die Datei ``03_grading_results.raw.json`` fasst die erfolgreichen
Einzelbewertungen einer studentischen Bearbeitung zusammen. Die
Modellantwort für eine einzelne Blattaufgabe enthält zunächst
``points``, ``max_points``, ``assessment_items``, ``summary`` und
``student_feedback``. Erst beim Zusammenführen ergänzt die Pipeline
beispielsweise ``target_path``, ``display_label`` und den Gesamtstatus.

Schematisches Beispiel einer vollständig bewerteten Blattaufgabe:

.. code-block:: json

   {
     "status": "complete",
     "student_id": "beispiel_01",
     "points": 1,
     "max_points": 1,
     "graded_task_count": 1,
     "failed_task_count": 0,
     "task_results": [
       {
         "target_path": "tasks[0].subtasks[0]",
         "display_label": "Aufgabe 1 / a)",
         "points": 1,
         "max_points": 1,
         "assessment_items": [
           {
             "id": "item_001",
             "description": "Leihfrist",
             "points": 1,
             "max_points": 1,
             "comment": "Die Leihfrist wurde richtig angegeben."
           }
         ],
         "summary": "Die Antwort ist korrekt.",
         "student_feedback": "Die Leihfrist beträgt drei Wochen."
       }
     ],
     "failed_tasks": []
   }

.. list-table:: Wichtige Felder
   :header-rows: 1
   :widths: 34 66

   * - Feld
     - Bedeutung
   * - ``task_results``
     - Erfolgreich eingelesene Bewertungen einzelner Blattaufgaben.
   * - ``assessment_items``
     - Bewertete Einzelaspekte mit ``id``, ``description``, ``points``,
       ``max_points`` und ``comment``.
   * - ``summary`` / ``student_feedback``
     - Zusammenfassung der Bewertung bzw. Rückmeldung an Studierende.
   * - ``failed_tasks``
     - Nicht bewertete Aufgaben mit ``target_path``, ``display_label``,
       ``status: "failed"`` und gegebenenfalls ``failure_tag``.
   * - ``graded_task_count`` / ``failed_task_count``
     - Anzahl erfolgreicher bzw. fehlgeschlagener Einzelbewertungen.
   * - ``status``
     - ``complete`` ohne fehlgeschlagene Aufgaben, sonst ``incomplete``.
   * - ``points`` / ``max_points`` (Gesamtergebnis)
     - Summen über die erfolgreichen Einzelbewertungen, **nur wenn**
       keine Aufgabe fehlgeschlagen ist und alle Einzelpunktwerte vorliegen;
       andernfalls ``null``.

Eine fehlgeschlagene Bewertung steht in ``failed_tasks`` und nicht
mit null Punkten in ``task_results``. Fehlende und tatsächlich
vergebene null Punkte dürfen nicht verwechselt werden. Ein Ergebnis
kann auch bei ``status: "complete"`` unbekannte Gesamtpunktzahlen
enthalten, wenn Einzelpunktwerte fehlen: Der Status bezieht sich
auf fehlgeschlagene Aufgaben, nicht auf die Vollständigkeit der Punkte.

