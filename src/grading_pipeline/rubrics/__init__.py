"""Öffentliche Fassade der Rubric-Erzeugung."""

from .rubric_generation import (
    RubricGenerationPipeline,
    RubricGenerationResult,
)

__all__ = [
    "RubricGenerationPipeline",
    "RubricGenerationResult",
]
