"""Konfiguration der Sphinx-Dokumentation von grading_pipeline."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))

project = "GradingPipeline"
author = "Bachelorarbeit"
language = "de"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

root_doc = "index"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

autosummary_generate = True
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_preserve_defaults = True

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = False

html_theme = "alabaster"
html_title = "GradingPipeline – Dokumentation"
html_static_path = ["_static"]

latex_documents = [
    (
        "index",
        "grading-pipeline.tex",
        r"GradingPipeline-Dokumentation",
        author,
        "manual",
    )
]

# Verwende die mit der lokalen LaTeX-Installation verfügbaren Standardschriften,
# statt zusätzliche TeX-Gyre-Pakete für die API-Referenz vorauszusetzen.
latex_elements = {
    "fontpkg": "",
}
