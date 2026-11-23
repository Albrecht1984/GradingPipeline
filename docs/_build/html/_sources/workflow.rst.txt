Nutzungsleitfaden
=================

Der Beispieldatensatz enthält eine fiktive Kurzantwortaufgabe, eine
Musterlösung und eine unvollständige studentische Antwort. Unter
``examples/kurzantwort/documents/`` liegen die drei Eingabebilder.
``examples/kurzantwort/prepared/`` enthält von Hand erstellte Aufgabenbäume,
mit denen sich Validierung, Rubric-Erzeugung und Bewertung direkt starten lassen.

Für die Transkription braucht man ein Modell, das Bilder verarbeiten kann.
Das Ollama-Modell ``qwen3-vl:8b-instruct`` kann sowohl die Bilder lesen als
auch die anschließenden Textschritte ausführen. Starte den lokalen
Ollama-Server und lade das Modell mit ``ollama pull qwen3-vl:8b-instruct``.
Andere Verbindungen beschreibt die :doc:`cli`.

Dokumente aufbereiten
---------------------

Für jedes Dokument die drei Verarbeitungsschritte nacheinander ausführen
und anschließend die erzeugten Artefakte mit ``validate`` prüfen.
Für Musterlösung und studentische Lösung jeweils Bildname, Ausgabeordner und
``--document-type`` durch ``reference_solution`` beziehungsweise
``student_solution`` ersetzen.

.. code-block:: console

   python main.py extract --input examples/kurzantwort/documents/assignment.png --output-dir work/kurzantwort/assignment --document-type assignment --model qwen3-vl:8b-instruct
   python main.py extract-tasks --input work/kurzantwort/assignment --document-type assignment --model qwen3-vl:8b-instruct
   python main.py partition-tasks --input work/kurzantwort/assignment --model qwen3-vl:8b-instruct
   python main.py validate --input work/kurzantwort/assignment

Nach der Transkription den Seitentext auf ausgelassene Inhalte prüfen. Nach der
Aufgabenextraktion die erkannten Hauptaufgaben kontrollieren. Nach der
Partitionierung in allen drei Dokumenten Reihenfolge und Anzahl der Knoten auf
jeder Ebene vergleichen. Die Bewertung ordnet Knoten anhand ihrer Position im
Baum zu. Die Maximalpunkte für bewertbare Blätter stammen aus der Aufgabenstellung.
Die Dateinamen für manuelle Korrekturen stehen unter :doc:`artifacts`.

Optional Rubrics erzeugen
-------------------------

Das Textmodell erhält die Aufgabenstellung und die strukturgleiche Musterlösung.
Die Rubrics werden pro bewertbarem Blatt erzeugt und lassen sich vor der
Bewertung prüfen. Für die Bewertung kann der erzeugte Ordner mit
``--rubrics-dir work/kurzantwort/rubrics`` übergeben werden.

.. code-block:: console

   python main.py create-rubrics --assignment-dir work/kurzantwort/assignment --reference-solution-dir work/kurzantwort/reference_solution --output-dir work/kurzantwort/rubrics --model qwen3-vl:8b-instruct

Lösung bewerten
---------------

``grade`` verwendet mindestens Aufgabenstellung und studentische Lösung.
Das Beispiel bezieht auch die Musterlösung ein und läuft ohne Rubrics.
Für die Bewertung mit den zuvor erzeugten Rubrics ergänze
``--rubrics-dir work/kurzantwort/rubrics``.

.. code-block:: console

   python main.py grade --assignment-dir work/kurzantwort/assignment --reference-solution-dir work/kurzantwort/reference_solution --student-solution-dir work/kurzantwort/student_solution --output-dir work/kurzantwort/grading --model qwen3-vl:8b-instruct
   python main.py validate --input work/kurzantwort/grading

``04_grading_report.md`` fasst Bewertungen und Punkte zusammen.
``05_student_feedback.md`` enthält die Rückmeldungen je Bewertungseinheit.
Für einen Einstieg ab der Bewertung können die drei Eingabeverzeichnisse
auch auf die mitgelieferten Aufgabenbäume unter
``examples/kurzantwort/prepared/`` zeigen.

Zusatzkontext einer Teilaufgabe zuordnen
----------------------------------------

Lege in ``work/kurzantwort/context/`` die UTF-8-Datei ``kontext.md`` mit
dem gewünschten Zusatztext an. Für das Beispiel reicht der Satz
„Bibliotheken legen Leihfristen und Rückgaberegeln in ihrer Benutzungsordnung
fest.“ Speichere daneben ``context_map.json`` mit diesem Inhalt.

.. code-block:: json

   {
     "contexts": [
       {"target_path": "tasks[0].subtasks[0]", "files": ["kontext.md"]},
       {"target_path": "tasks[0].subtasks[1]", "files": []}
     ]
   }

Die Pfade bezeichnen die Teilaufgaben a) und b) des vorbereiteten Beispiels.
Die Datei gilt hier nur für a). Das Manifest enthält für jedes bewertbare
Blatt einen Eintrag. Dateipfade sind relativ zum Manifest und bleiben in
dessen Verzeichnis.

.. code-block:: console

   python main.py grade --model qwen3-vl:8b-instruct --assignment-dir examples/kurzantwort/prepared/assignment --reference-solution-dir examples/kurzantwort/prepared/reference_solution --student-solution-dir examples/kurzantwort/prepared/student_solution --context-map work/kurzantwort/context/context_map.json --output-dir work/kurzantwort/grading-context

Nach manueller Korrektur erneut bewerten
----------------------------------------

Kopiere die partitionierte studentische Lösung in einen Arbeitsordner und
speichere die korrigierte Fassung mit dem Zusatz ``.reviewed``.

.. code-block:: powershell

   New-Item -ItemType Directory -Force work/kurzantwort/student-review
   Copy-Item examples/kurzantwort/prepared/student_solution/06_task_partitioning.raw.json work/kurzantwort/student-review/06_task_partitioning.raw.json
   Copy-Item work/kurzantwort/student-review/06_task_partitioning.raw.json work/kurzantwort/student-review/06_task_partitioning.reviewed.json

Korrigiere in der Reviewed-Datei beispielsweise einen Transkriptionsfehler
im Feld ``markdown`` der betroffenen Teilaufgabe. Die Baumpositionen müssen
weiter zur Aufgabenstellung passen. Den Aufbau der Dateien erklärt
:doc:`json_formats`. Prüfe den Ordner und starte dann die Bewertung mit
diesem Eingabeordner.

.. code-block:: console

   python main.py validate --input work/kurzantwort/student-review
   python main.py grade --model qwen3-vl:8b-instruct --assignment-dir examples/kurzantwort/prepared/assignment --reference-solution-dir examples/kurzantwort/prepared/reference_solution --student-solution-dir work/kurzantwort/student-review --output-dir work/kurzantwort/grading-review

Die Bewertung liest bevorzugt ``06_task_partitioning.reviewed.json``. Der
eigene Ausgabeordner erlaubt es, den neuen Bericht mit einem vorherigen
Bericht zu vergleichen.
