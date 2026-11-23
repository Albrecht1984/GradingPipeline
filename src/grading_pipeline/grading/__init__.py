"""Öffentliche Fassade der Bewertungspipeline."""

from .grading import GradingPipeline, GradingPipelineResult
from .monolithic import MonolithicGradingPipeline, MonolithicGradingResult


__all__ = [
    "GradingPipeline",
    "GradingPipelineResult",
    "MonolithicGradingPipeline",
    "MonolithicGradingResult",
]
