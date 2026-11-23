"""Einlesen JSON-basierter Modellantworten."""

from __future__ import annotations

import json
from typing import Any


def parse_model_json_object(
    raw: str,
    *,
    response_label: str,
) -> dict[str, Any]:
    """Parst ein Modell-JSON-Objekt und entfernt höchstens vollständige Code-Fences."""
    candidate = raw.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        first_newline = candidate.find("\n")
        if first_newline != -1:
            candidate = candidate[first_newline + 1 : -3].strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Die {response_label} enthaelt ungueltiges JSON: {error}"
        ) from error
    if not isinstance(parsed, dict):
        raise ValueError(f"Die {response_label} ist kein JSON-Objekt.")
    return parsed
