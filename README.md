# GradingPipeline

GradingPipeline bereitet Aufgabenstellungen, Musterlösungen und studentische
Bearbeitungen aus PDF-Dateien oder Bildern auf. Aus der erkannten
Aufgabenstruktur bildet sie Bewertungseinheiten und erstellt Berichte mit
Punkten und Rückmeldungen. Musterlösungen, Rubrics, Textkontext und manuell
zugeordnete Bilder können die Bewertung ergänzen.

Die Pipeline speichert die Ergebnisse jeder Stufe. Dadurch lassen sich
Transkription und Aufgabenbaum prüfen, korrigieren und gezielt weiterverarbeiten.
Für Modellaufrufe unterstützt sie Ollama und OpenAI.

## Installation

Getestet mit Python 3.14. Die Befehle starten im Repository-Stamm.

```console
python -m venv .venv
```

Unter Windows lässt sich die Umgebung in PowerShell aktivieren.

```powershell
.\.venv\Scripts\Activate.ps1
```

Unter Linux oder macOS geht das in der Shell.

```sh
source .venv/bin/activate
```

```console
python -m pip install -r requirements.txt
python main.py --help
```

## Beispieldatensatz

Das synthetische Beispiel enthält drei Eingabebilder und die dazugehörigen
vorbereiteten Aufgabenbäume. Dieser Befehl prüft einen Aufgabenbaum ohne Modell
oder Zugangsschlüssel.

```console
python main.py validate --input examples/kurzantwort/prepared/assignment
```

Die Konsole meldet `valid`.

### Bewertung mit Ollama

1. [Ollama installieren](https://ollama.com/download). Unter Windows läuft
   Ollama nach der Installation im Hintergrund. Falls noch kein Server läuft,
   starte die Ollama-App oder führe `ollama serve` in einem separaten Terminal aus.
   Die Pipeline verbindet sich standardmäßig mit `http://localhost:11434`.

2. Das Modell herunterladen und prüfen, ob es lokal verfügbar ist.

   ```console
   ollama pull qwen3-vl:8b-instruct
   ollama ls
   ```

   In der Liste sollte `qwen3-vl:8b-instruct` stehen. Der Download benötigt
   rund 6,2 GB Speicherplatz. Die Modellseite nennt die für diesen Tag
   erforderliche Ollama-Version. [Modell bei Ollama](https://ollama.com/library/qwen3-vl:8b-instruct)

3. Die vorbereitete Beispielabgabe aus dem Repository-Stamm bewerten.

   ```console
   python main.py grade --provider ollama --model qwen3-vl:8b-instruct --assignment-dir examples/kurzantwort/prepared/assignment --reference-solution-dir examples/kurzantwort/prepared/reference_solution --student-solution-dir examples/kurzantwort/prepared/student_solution --output-dir work/kurzantwort/grading
   ```

Der Bericht liegt unter `work/kurzantwort/grading/04_grading_report.md`.
Im Beispiel ist die erste Antwort korrekt und die zweite falsch. Die fachlich
erwartete Bewertung ist 1 von 2 Punkten. Die konkrete Modellausgabe kann davon
abweichen.

Für einen vollständigen Lauf ab den Eingabebildern führt der
[Nutzungsleitfaden](docs/workflow.rst) durch die Dokumentaufbereitung.
Die Befehle dort verwenden dasselbe Ollama-Modell für die Bild- und Textschritte.

Bei vielen Dokumenten bieten sich eigene Batchskripte an, die die
CLI-Befehle für jede Eingabe aufrufen.

## Dokumentation

- [Nutzungsleitfaden](docs/workflow.rst) mit allen Stufen und Modellvoraussetzungen
- [CLI-Referenz](docs/cli.rst) mit Befehlen und gemeinsamen Optionen
- [Artefakte und Wiederanlauf](docs/artifacts.rst) mit Korrekturstellen und Datenformaten
- [Python-API](docs/api/index.rst) mit öffentlicher API und Entwicklerreferenz

Die navigierbare HTML-Doku mit Signaturen und Quellcodeverweisen lässt sich
lokal bauen. Einstiegspunkt ist anschließend `docs/_build/html/index.html`.

```console
python -m pip install -r docs/requirements.txt
python -m sphinx -E -a -W --keep-going -b html docs docs/_build/html
```
