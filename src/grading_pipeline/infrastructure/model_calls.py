"""Gemeinsame LangChain-Modellaufrufe der Pipelinestufen."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import html
from pathlib import Path
import time
from typing import Callable, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from grading_pipeline.models.responses import response_text
from .progress import ProgressHeartbeat


@dataclass(frozen=True)
class MultimodalImage:
    """Bündelt Bilddatei und sichtbare ID eines Modellinputs."""

    image_id: str
    path: Path


@dataclass(frozen=True)
class MultimodalImageGroup:
    """Bündelt aufeinanderfolgende Bilder derselben sichtbaren Quelle."""

    label: str
    images: tuple[MultimodalImage, ...]


def invoke_json_model(
    model: BaseChatModel,
    prompt: str,
    *,
    progress: Callable[[str], None],
    heartbeat_label: str,
    result_label: str,
) -> tuple[AIMessage, float]:
    """Ruft ein Modell im JSON-Modus auf und meldet Laufzeit und Antwortgröße."""
    started_at = time.perf_counter()
    with ProgressHeartbeat(progress, label=heartbeat_label):
        response = invoke_chat_model(
            model,
            [HumanMessage(content=prompt)],
            json_mode=True,
        )
    content = response_text(response)
    if not content.strip():
        raise RuntimeError("Das Modell lieferte eine leere Antwort.")
    progress(
        f"{result_label}: Antwort nach {time.perf_counter() - started_at:.1f} s "
        f"erhalten ({len(content)} Zeichen)."
    )
    return response, started_at


def invoke_vision_model(
    model: BaseChatModel,
    prompt: str,
    image_bytes: bytes,
) -> AIMessage:
    """Ruft ein Modell mit einer eingebetteten Bildnachricht auf."""
    if not image_bytes:
        raise ValueError("Das Seitenbild ist leer.")
    media_type = detect_image_media_type(image_bytes) or "image/png"
    image_url = f"data:{media_type};base64," + base64.b64encode(image_bytes).decode(
        "ascii"
    )
    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
    )
    return invoke_chat_model(model, [message], json_mode=False)


def invoke_multimodal_json_model(
    model: BaseChatModel,
    prompt: str,
    image_groups: Sequence[MultimodalImageGroup],
    *,
    progress: Callable[[str], None],
    heartbeat_label: str,
    result_label: str,
    json_mode: bool = True,
) -> tuple[AIMessage, float]:
    """Ruft ein Vision-Modell mit explizit gruppierten Bildern auf."""

    content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
    image_count = 0
    for group in image_groups:
        group_label = html.escape(group.label, quote=True)
        content.append(
            {"type": "text", "text": f'<BILDGRUPPE quelle="{group_label}">'}
        )
        for image in group.images:
            image_bytes = image.path.read_bytes()
            if not image_bytes:
                raise ValueError(f"Das Bildsupplement ist leer: {image.path}")
            media_type = detect_image_media_type(image_bytes)
            if media_type is None:
                raise ValueError(f"Nicht unterstuetztes Bildsupplement: {image.path}")
            image_url = (
                f"data:{media_type};base64,"
                + base64.b64encode(image_bytes).decode("ascii")
            )
            image_id = html.escape(image.image_id, quote=True)
            content.extend(
                (
                    {"type": "text", "text": f'<BILD id="{image_id}" />'},
                    {"type": "image_url", "image_url": {"url": image_url}},
                )
            )
            image_count += 1
        content.append({"type": "text", "text": "</BILDGRUPPE>"})
    started_at = time.perf_counter()
    with ProgressHeartbeat(progress, label=heartbeat_label):
        response = invoke_chat_model(
            model,
            [HumanMessage(content=content)],
            json_mode=json_mode,
        )
    response_content = response_text(response)
    if not response_content.strip():
        raise RuntimeError("Das Modell lieferte eine leere Antwort.")
    progress(
        f"{result_label}: Antwort nach {time.perf_counter() - started_at:.1f} s "
        f"erhalten ({len(response_content)} Zeichen, {image_count} Bild(er))."
    )
    return response, started_at


def invoke_chat_model(
    model: BaseChatModel,
    messages: Sequence[BaseMessage],
    *,
    json_mode: bool,
) -> AIMessage:
    """Ruft ein LangChain-Modell mit dessen providerbezogenem JSON-Schalter auf."""
    options: dict[str, object] = {}
    provider = str(getattr(model, "provider", "")).lower()
    if json_mode and (isinstance(model, ChatOllama) or provider == "ollama"):
        options["format"] = "json"
    elif json_mode and (isinstance(model, ChatOpenAI) or provider == "openai"):
        options["response_format"] = {"type": "json_object"}
    response = model.invoke(list(messages), **options)
    if not isinstance(response, AIMessage):
        raise RuntimeError("Das Modell lieferte keine gueltige LangChain-Antwort.")
    return response


def detect_image_media_type(image_bytes: bytes) -> str | None:
    """Erkennt den MIME-Typ unterstützter Bilder anhand ihrer Dateisignatur."""
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if image_bytes.startswith(b"BM"):
        return "image/bmp"
    if image_bytes.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    return None
