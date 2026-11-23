"""Auswertung und Serialisierung von LangChain-Modellantworten."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from langchain_core.messages import AIMessage


@dataclass(frozen=True, slots=True)
class ModelMetrics:
    """Normalisierte Laufzeit-, Modell- und Tokenmetriken einer AIMessage."""

    resolved_model: str | None = None
    provider_total_seconds: float | None = None
    provider_load_seconds: float | None = None
    prompt_evaluation_seconds: float | None = None
    generation_seconds: float | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


def response_artifact(response: AIMessage) -> dict[str, Any]:
    """Serialisiert eine AIMessage im stabilen Projektartefakt."""
    return {
        "content": response_text(response),
        "provider_payload": response.model_dump(mode="json", exclude_none=True),
    }


def response_text(response: AIMessage) -> str:
    """Liest Text aus einfacher oder blockbasierter LangChain-Ausgabe."""
    if isinstance(response.content, str):
        return response.content
    parts: list[str] = []
    for block in response.content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)


def model_metrics(response: AIMessage) -> ModelMetrics:
    """Normalisiert LangChain-Nutzungsdaten und Provider-Metadaten."""
    metadata = response.response_metadata
    usage = response.usage_metadata or {}
    input_details = usage.get("input_token_details", {})
    if not isinstance(input_details, Mapping):
        input_details = {}
    model = metadata.get("model") or metadata.get("model_name")
    return ModelMetrics(
        resolved_model=model.strip() if isinstance(model, str) and model.strip() else None,
        provider_total_seconds=_nanoseconds_to_seconds(metadata.get("total_duration")),
        provider_load_seconds=_nanoseconds_to_seconds(metadata.get("load_duration")),
        prompt_evaluation_seconds=_nanoseconds_to_seconds(
            metadata.get("prompt_eval_duration")
        ),
        generation_seconds=_nanoseconds_to_seconds(metadata.get("eval_duration")),
        input_tokens=_optional_nonnegative_int(usage.get("input_tokens")),
        cached_input_tokens=_optional_nonnegative_int(input_details.get("cache_read")),
        output_tokens=_optional_nonnegative_int(usage.get("output_tokens")),
        total_tokens=_optional_nonnegative_int(usage.get("total_tokens")),
    )


def _optional_nonnegative_int(value: Any) -> int | None:
    """Übernimmt ausschließlich nichtnegative ganzzahlige Zähler."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _nanoseconds_to_seconds(value: Any) -> float | None:
    """Konvertiert endliche nichtnegative Nanosekunden in Sekunden."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        return None
    return float(value) / 1_000_000_000
