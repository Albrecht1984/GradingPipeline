"""Erzeugung validierter Jinja2-Promptvorlagen für LangChain."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from langchain_core.prompts import PromptTemplate


def create_prompt_template(
    template: str,
    *,
    variables: Iterable[str],
    prompt_label: str,
) -> PromptTemplate:
    """Erzeugt eine Jinja2-Vorlage und prüft ihre Projektvariablen."""

    required_variables = tuple(dict.fromkeys(variables))
    prompt = PromptTemplate.from_template(
        template,
        template_format="jinja2",
    )
    missing = [
        name
        for name in required_variables
        if name not in prompt.input_variables
    ]
    if missing:
        placeholders = ", ".join("{{ " + name + " }}" for name in missing)
        raise ValueError(
            f"Der {prompt_label} enthaelt nicht alle erforderlichen "
            f"Platzhalter: {placeholders}"
        )

    return prompt


def render_prompt_template(
    template: str,
    *,
    values: Mapping[str, str],
    prompt_label: str,
) -> str:
    """Rendert eine Projektvorlage einmalig mit LangChains PromptTemplate."""

    prompt = create_prompt_template(
        template,
        variables=values,
        prompt_label=prompt_label,
    )
    return prompt.format(**values)
