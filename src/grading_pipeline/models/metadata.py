"""Auswertung der Konfiguration und Laufzeitgrenzen eines Chatmodells."""

from __future__ import annotations

from typing import Any, Mapping

from langchain_core.language_models import BaseChatModel


def model_identity(
    model: BaseChatModel | Any,
    *,
    json_mode: bool,
) -> dict[str, Any]:
    """Liefert die für Cache und Statistik relevante Modellidentität."""
    metadata = getattr(model, "metadata", None)
    if isinstance(metadata, Mapping):
        stored = metadata.get("own_pix_identity")
        if isinstance(stored, Mapping):
            identity = dict(stored)
            identity["response_format"] = "json" if json_mode else "text"
            return identity

    provider = getattr(model, "provider", model.__class__.__name__)
    name = getattr(model, "model", getattr(model, "model_name", None))
    base_url = getattr(model, "base_url", getattr(model, "openai_api_base", None))
    identity = {
        "provider": str(provider).lower(),
        "model": name,
        "base_url": str(base_url).rstrip("/") if base_url is not None else None,
        "response_format": "json" if json_mode else "text",
    }
    temperature = getattr(model, "temperature", None)
    if temperature is not None:
        identity["generation_options"] = {"temperature": temperature}
    return identity


def model_timeout(model: BaseChatModel | Any) -> float | None:
    """Liest das für Statistiken gespeicherte Zeitlimit eines Modells."""
    metadata = getattr(model, "metadata", None)
    if isinstance(metadata, Mapping):
        timeout = metadata.get("own_pix_timeout")
        if isinstance(timeout, (int, float)) and not isinstance(timeout, bool):
            return float(timeout)
    timeout = getattr(model, "timeout", None)
    if isinstance(timeout, (int, float)) and not isinstance(timeout, bool):
        return float(timeout)
    return None


def model_label(model: BaseChatModel | Any) -> tuple[str, str | None]:
    """Gibt angeforderten Modellnamen und optionalen Endpunkt zurück."""
    identity = model_identity(model, json_mode=False)
    return str(identity.get("model") or model.__class__.__name__), identity.get("base_url")
