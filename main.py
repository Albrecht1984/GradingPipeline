"""Startet die lokale ``grading_pipeline``-Kommandozeile direkt aus dem Projektordner."""

from pathlib import Path
import sys


# Add the local src directory to Python's module search path so the package can
# be run directly from the repository without installing it first.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

# Import the actual command-line entry point after grading_pipeline has become importable.
from grading_pipeline.cli import main


# Start the CLI only when this file is executed, not when it is imported.
if __name__ == "__main__":
    main()
