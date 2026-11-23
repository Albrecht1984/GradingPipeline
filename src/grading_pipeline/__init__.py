"""Öffentliche Paketoberfläche für Extraktion und Bewertung."""

# Python führt dieses Modul beim ersten Paketimport aus. Die zentralen
# Pipelinetypen werden hier erneut exportiert, damit Aufrufer sie direkt aus
# grading_pipeline importieren können.
from grading_pipeline.extraction import (
    VisualExtractionResult,
    TaskExtractionPipeline,
    TaskPartitioningPipeline,
    TaskExtractionResult,
    TaskPartitioningResult,
    VisualExtractionPipeline,
)
from grading_pipeline.grading import GradingPipeline, GradingPipelineResult


# Diese Namen bilden die unterstützte öffentliche Paketoberfläche.
__all__ = [
    "VisualExtractionResult",
    "GradingPipeline",
    "GradingPipelineResult",
    "TaskExtractionPipeline",
    "TaskPartitioningPipeline",
    "TaskExtractionResult",
    "TaskPartitioningResult",
    "VisualExtractionPipeline",
]
