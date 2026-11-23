"""Konfiguration und Erzeugung der verwendeten LangChain-Chatmodelle."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Mapping

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI


@dataclass(frozen=True)
class ChatModelConfig:
    """Bündelt die Einstellungen zur Erzeugung eines LangChain-Modells."""

    provider: str
    model: str
    ollama_base_url: str = "http://localhost:11434"
    ollama_num_ctx: int | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key_env: str = "OPENAI_API_KEY"
    timeout: float = 1800.0
    temperature: float | None = None


def create_chat_model(config: ChatModelConfig) -> BaseChatModel:
    """Erzeugt unmittelbar ChatOllama oder ChatOpenAI."""
    provider = config.provider.strip().lower()
    model_name = config.model.strip()
    if not model_name:
        raise ValueError("Ein Modell muss angegeben werden.")

    if provider == "ollama":
        identity = {
            "provider": provider,
            "model": model_name,
            "base_url": config.ollama_base_url.rstrip("/"),
        }
        generation_options: dict[str, int | float] = _temperature_options(
            config.temperature
        )
        if config.ollama_num_ctx is not None:
            generation_options["num_ctx"] = config.ollama_num_ctx
        if generation_options:
            identity["generation_options"] = generation_options
        transport_options = {"timeout": config.timeout}
        return ChatOllama(
            model=model_name,
            base_url=identity["base_url"],
            reasoning=False,
            client_kwargs=transport_options,
            async_client_kwargs=transport_options,
            metadata=_model_metadata(identity, config.timeout),
            **generation_options,
        )

    if provider == "openai":
        identity = {
            "provider": provider,
            "model": model_name,
            "base_url": config.openai_base_url.rstrip("/"),
        }
        generation_options = _temperature_options(config.temperature)
        if generation_options:
            identity["generation_options"] = generation_options
        return ChatOpenAI(
            model=model_name,
            base_url=identity["base_url"],
            api_key=lambda: _required_api_key(config.openai_api_key_env),
            timeout=config.timeout,
            store=False,
            use_responses_api=True,
            metadata=_model_metadata(identity, config.timeout),
            **generation_options,
        )

    raise ValueError(
        f"Unbekannter Modell-Provider: {config.provider!r}. "
        "Erlaubt: ollama, openai."
    )


def _temperature_options(temperature: float | None) -> dict[str, float]:
    """Gibt eine explizite Temperatur weiter und lässt Providerdefaults unangetastet."""

    return {} if temperature is None else {"temperature": temperature}


def _model_metadata(identity: Mapping[str, Any], timeout: float) -> dict[str, Any]:
    """Verpackt Projektmetadaten für LangChains bestehendes metadata-Feld."""
    return {"own_pix_identity": dict(identity), "own_pix_timeout": timeout}


def _required_api_key(variable: str) -> str:
    """Liest den OpenAI-Schlüssel aus der konfigurierten Umgebungsvariable."""
    api_key = os.environ.get(variable)
    if not api_key:
        raise ValueError(
            f"Die Umgebungsvariable {variable!r} mit dem OpenAI-API-Key ist nicht gesetzt."
        )
    return api_key
