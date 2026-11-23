"""Erzeugt portable Statistiken fuer eine Pipeline-Einheit."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Callable, Mapping

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from .json_io import write_json_atomic
from grading_pipeline.models.metadata import model_identity, model_timeout
from grading_pipeline.models.responses import ModelMetrics, model_metrics, response_text


def write_model_call_statistics(
    path: Path,
    *,
    model: BaseChatModel,
    response: AIMessage,
    stage: str,
    model_input: str,
    started_at: float,
    output_text: str | None = None,
    complexity: Mapping[str, int] | None = None,
    json_mode: bool = True,
    warn: Callable[[str], None] | None = None,
) -> dict[str, Any] | None:
    """Schreibt Statistiken; ein Nebenartefaktfehler stoppt die Pipeline nicht."""

    try:
        return _write_model_call_statistics(
            path,
            model=model,
            response=response,
            stage=stage,
            model_input=model_input,
            started_at=started_at,
            output_text=output_text,
            complexity=complexity,
            json_mode=json_mode,
        )
    except (OSError, TypeError, ValueError) as exc:
        if warn is not None:
            warn(f"WARNUNG: Statistikdatei konnte nicht geschrieben werden: {path}: {exc}")
        return None


def _write_model_call_statistics(
    path: Path,
    *,
    model: BaseChatModel,
    response: AIMessage,
    stage: str,
    model_input: str,
    started_at: float,
    output_text: str | None = None,
    complexity: Mapping[str, int] | None = None,
    json_mode: bool = True,
) -> dict[str, Any]:
    """Schreibt die gemeinsamen Statistiken eines Modellaufrufs."""

    metrics = model_metrics(response)
    result_text = response_text(response) if output_text is None else output_text
    model_data = model_payload(
        model_identity(model, json_mode=json_mode), metrics, model_timeout(model)
    )
    if stage in {"visual_extraction", "task_extraction"}:
        model_data.pop("response_format", None)
    payload: dict[str, Any] = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "model": model_data,
        "timing": timing_payload(metrics, time.perf_counter() - started_at),
        "tokens": token_payload(metrics),
        "complexity": {
            "input_characters": len(model_input),
            "output_characters": len(result_text),
            **dict(complexity or {}),
        },
    }
    write_json_atomic(path, payload)
    return payload


def timing_payload(
    metrics: ModelMetrics,
    wall_seconds: float,
) -> dict[str, float | None]:
    """Verbindet die gemessene Laufzeit mit normalisierten Providerzeiten."""

    return {
        "wall_seconds": wall_seconds,
        "provider_total_seconds": metrics.provider_total_seconds,
        "provider_load_seconds": metrics.provider_load_seconds,
        "prompt_evaluation_seconds": metrics.prompt_evaluation_seconds,
        "generation_seconds": metrics.generation_seconds,
    }


def token_payload(metrics: ModelMetrics) -> dict[str, int | float | None]:
    """Berechnet Zählwerte und Raten aus normalisierten Modellmetriken."""

    input_tokens = metrics.input_tokens
    output_tokens = metrics.output_tokens
    total_tokens = metrics.total_tokens
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return {
        "input": input_tokens,
        "cached_input": metrics.cached_input_tokens,
        "output": output_tokens,
        "total": total_tokens,
        "input_per_second": rate(input_tokens, metrics.prompt_evaluation_seconds),
        "output_per_second": rate(output_tokens, metrics.generation_seconds),
    }


def model_payload(
    identity: Mapping[str, Any],
    metrics: ModelMetrics,
    timeout_seconds: float | None,
) -> dict[str, Any]:
    """Erfasst die verwendete Modellkennung und die übrigen Statistikangaben."""

    model_data = dict(identity)
    model_data.pop("base_url", None)
    requested_model = model_data.pop("model", None)
    return {
        **model_data,
        "used_model": metrics.resolved_model or requested_model,
        "timeout_seconds": timeout_seconds,
    }


def rate(count: int | None, seconds: float | None) -> float | None:
    """Berechnet eine Rate, sofern Zaehler und positive Laufzeit vorliegen."""

    if count is None or seconds is None or seconds <= 0:
        return None
    return count / seconds
