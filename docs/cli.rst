CLI-Referenz
============

Alle Befehle starten mit ``python main.py``. Für die vollständige
Argumentliste mit Standardwerten ``--help`` an den jeweiligen Befehl anhängen.

.. list-table::
   :header-rows: 1
   :widths: 26 74

   * - Befehl
     - Eingabe und Zweck
   * - ``extract``
     - PDF oder Bild rendern und seitenweise transkribieren.
   * - ``prepare-images``
     - Bildausschnitte aus gerenderten Seiten und vorhandenen BBOX-Markierungen
       modellfrei erzeugen oder aktualisieren.
   * - ``extract-tasks``
     - Hauptaufgaben aus dem zusammengeführten Seitentext extrahieren.
   * - ``partition-tasks``
     - Hauptaufgaben rekursiv in Einleitungen und Unteraufgaben gliedern.
   * - ``create-rubrics``
     - Rubrics anhand partitionierter Aufgabenstellung und Musterlösung erzeugen.
   * - ``grade``
     - Partitionierte Bearbeitung pro Blattaufgabe bewerten. Musterlösung,
       Rubrics und zusätzlicher Textkontext sind optional.
   * - ``grade-with-images``
     - Pro Blattaufgabe mit einem Vision-Modell bewerten und manuell zugeordnete
       Bilder in den Modellinput aufnehmen.
   * - ``grade-monolithic``
     - Die vollständigen Dokumente in einem multimodalen Aufruf bewerten.
       Der Eingabeordner enthält die drei Rollen als Unterordner mit jeweils
       genau einer PDF- oder Bilddatei.
   * - ``validate``
     - Unterstützte Artefakte eines Ordners modellfrei prüfen und Befunde
       auf der Konsole ausgeben.

Modelloptionen
--------------

``--model`` gibt den Modellnamen an. ``--provider`` akzeptiert
``ollama`` oder ``openai`` und kann für jede Stufe einzeln gewählt werden.
Bei Ollama steuern ``--ollama-base-url`` und ``--ollama-num-ctx``
Endpunkt und optionales Kontextfenster. Bei OpenAI steuert
``--openai-base-url`` den Endpunkt. Der Schlüssel wird aus der durch
``--openai-api-key-env`` benannten Umgebungsvariable gelesen
(Standard ``OPENAI_API_KEY``).

``--prompt-file`` überschreibt die jeweilige Vorlage aus ``prompts/``.
``--timeout`` setzt das Zeitlimit für einen Modellaufruf in Sekunden.
Ohne ``--temperature`` gilt der Modell- oder Providerstandard.
``--overwrite`` und ``--verbose`` erwarten ``true`` oder ``false``.
Mit ``--overwrite true`` ignoriert eine Modellstufe ihren Cache.

Bewertungsoptionen
------------------

``--context`` kann mehrfach angegeben werden und fügt Textdateien jeder
Bewertungseinheit hinzu. ``--context-map`` ordnet Kontextdateien anhand
der strukturellen Blattpfade zu. Das Manifest ist ein JSON-Objekt mit der
Liste ``contexts``. Jeder Eintrag enthält einen ``target_path`` und eine
Liste ``files`` mit Pfaden relativ zum Manifest.
Alle Blattpfade müssen enthalten sein. Eine leere Liste steht für ein Blatt
ohne Zusatzkontext. ``--skip-target`` markiert einen Blattpfad gezielt als
Laufzeitfehler und überspringt den Modellaufruf für dieses Ziel.
