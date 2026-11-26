"""Multimodal image inspection MCP tool."""

from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from ...utils import support
from ...utils.subagents import loop, runtime
from ...utils.subagents.resolve import resolve_continue
from ...utils.subagents.roles import get_role
from ...utils.support import describe, inside

_SUPPORTED_IMAGE_MEDIA_TYPES: frozenset[str] = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/bmp",
        "image/tiff",
    }
)
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),
    (b"BM", "image/bmp"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
)
_IMAGE_MAX_BYTES: int = 20 * 1024 * 1024


def _detected_media_type(path: Path, content: bytes) -> str | None:
    """Infer an image media type from extension or file signature."""
    guessed, _encoding = mimetypes.guess_type(path.name)
    if isinstance(guessed, str) and guessed in _SUPPORTED_IMAGE_MEDIA_TYPES:
        return guessed
    for signature, media_type in _IMAGE_SIGNATURES:
        if content.startswith(signature):
            if media_type == "image/webp" and content[8:12] != b"WEBP":
                continue
            return media_type
    return None


def _image_backend_setup_hint() -> str:
    """Return actionable guidance when no image-capable subagent LLM is available."""
    return (
        "Image analysis is unavailable because no subagent LLM is configured. "
        "Configure a model by either: "
        "(1) setting OPENAI_API_KEY (and optional SUBAGENT_BACKEND=direct:openai), "
        "(2) setting ANTHROPIC_API_KEY (and optional SUBAGENT_BACKEND=direct:anthropic), "
        "(3) configuring Continue models for this workspace, or "
        "(4) running a local Ollama vision model with SUBAGENT_BACKEND=local:ollama."
    )


def _run_generalist_image_prompt(
    *, prompt: str, image_base64: str, media_type: str, output_mode: str
) -> tuple[str, str, dict[str, str] | None]:
    """Run a one-shot generalist prompt with image input and return backend/model/result."""
    backend = runtime._backend()
    role = get_role("generalist")
    if role is None:
        raise RuntimeError("generalist role is not configured")

    result_format = role.result_format
    if output_mode == "concise":
        result_format = (
            "Answer the user's question directly in 1-3 sentences. "
            "Do not return planning templates or multi-section frameworks unless explicitly requested."
        )

    system_prompt = "\n".join(
        [
            role.system_prompt,
            f"Target result format: {result_format}",
        ]
    )
    max_tokens = max(256, min(role.max_tokens, 4096))
    message_content: list = [
        {"type": "text", "text": prompt},
        {
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{image_base64}"},
        },
    ]
    anthropic_content: list = [
        {"type": "text", "text": prompt},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_base64,
            },
        },
    ]

    if backend == "sampling":
        if runtime._SAMPLING_CALLBACK is None:
            raise ValueError("Sampling callback is not configured")
        result = runtime._SAMPLING_CALLBACK(
            system_prompt,
            [{"role": "user", "content": message_content}],
            max_tokens,
        )
        return backend, result, None

    if backend == "cooperative" and not runtime._COOP_EXPLICIT:
        raise ValueError("No subagent LLM available")
    if backend == "cooperative":
        raise RuntimeError("Image inspection is unsupported for cooperative backend")

    if backend.startswith("continue:"):
        resolved = resolve_continue()
        if resolved is None:
            raise ValueError("No subagent LLM available")
        model = resolved.model
        model_summary = model.safe_summary()
        if model.provider == "anthropic":
            result = loop._complete_anthropic(
                model.api_key or "",
                system_prompt,
                [{"role": "user", "content": anthropic_content}],
                max_tokens,
                model=model.model,
                base_url=model.api_base,
                headers=model.headers,
            )
            return backend, result, model_summary
        if not loop.continue_provider_supported(model.provider):
            raise RuntimeError(f"Unsupported continue provider: {model.provider}")
        result = loop._complete_openai_compatible(
            loop._continue_base_url(model.provider, model.api_base),
            model.model,
            model.api_key,
            system_prompt,
            [{"role": "user", "content": message_content}],
            max_tokens,
            headers=model.headers,
        )
        return backend, result, model_summary

    if backend == "direct:openai":
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise ValueError("OPENAI_API_KEY is not set")
        model = os.environ.get("SUBAGENT_MODEL_OPENAI", "gpt-4o-mini")
        result = loop._complete_openai_compatible(
            "https://api.openai.com/v1",
            model,
            key,
            system_prompt,
            [{"role": "user", "content": message_content}],
            max_tokens,
        )
        return backend, result, {"provider": "openai", "model": model, "name": model}

    if backend == "direct:anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        model = os.environ.get("SUBAGENT_MODEL_ANTHROPIC", "claude-3-5-haiku-latest")
        result = loop._complete_anthropic(
            key,
            system_prompt,
            [{"role": "user", "content": anthropic_content}],
            max_tokens,
            model=model,
        )
        return (
            backend,
            result,
            {
                "provider": "anthropic",
                "model": model,
                "name": model,
            },
        )

    if backend == "local:ollama":
        model = os.environ.get("SUBAGENT_MODEL_LOCAL", "llama3.2-vision")
        result = loop._complete_openai_compatible(
            "http://127.0.0.1:11434/v1",
            model,
            None,
            system_prompt,
            [{"role": "user", "content": message_content}],
            max_tokens,
        )
        return backend, result, {"provider": "ollama", "model": model, "name": model}

    raise RuntimeError(f"Unsupported subagent backend: {backend}")


def inspect_image(
    image_path: Annotated[
        str,
        Field(
            min_length=1,
            description="Workspace-relative image file path to inspect. (Required: True)",
        ),
    ],
    prompt: Annotated[
        str,
        Field(
            description="Prompt sent to the generalist subagent with the image input. (Required: True)"
        ),
    ],
    output_mode: Annotated[
        Literal["concise", "detailed"],
        Field(
            description=(
                "Output verbosity for the model response: concise returns a direct answer-first response, "
                "while detailed allows longer structured output. (Required: False)"
            )
        ),
    ] = "concise",
) -> dict:
    """Inspect an image by prompting the generalist role with multimodal input."""
    prompt_text = prompt.strip()
    if not prompt_text:
        return {
            "error_code": "empty_prompt",
            "message": "prompt must not be empty.",
        }

    mode = output_mode.strip().lower()
    if mode not in {"concise", "detailed"}:
        return {
            "error_code": "invalid_output_mode",
            "message": "output_mode must be one of: concise, detailed.",
        }
    try:
        path = inside(image_path, must_exist=True)
    except FileNotFoundError:
        return {
            "error_code": "not_found",
            "path": image_path,
            "message": f"File not found: {image_path}",
        }
    except ValueError:
        return {
            "error_code": "path_escape",
            "path": image_path,
            "message": support.path_escape_message(image_path),
        }
    except OSError as exc:
        return {
            "error_code": "io_error",
            "path": image_path,
            "message": f"{exc.strerror or 'Path could not be resolved'}: {image_path}",
        }

    if not path.is_file():
        return {
            "error_code": "not_a_file",
            "path": image_path,
            "message": f"Not a file: {image_path}",
        }
    try:
        data = path.read_bytes()
    except OSError as exc:
        return {
            "error_code": "io_error",
            "path": image_path,
            "message": f"{exc.strerror or 'File could not be read'}: {image_path}",
        }
    if len(data) > _IMAGE_MAX_BYTES:
        return {
            "error_code": "file_too_large",
            "path": image_path,
            "message": (
                f"Image exceeds {_IMAGE_MAX_BYTES // (1024 * 1024)} MiB limit: {image_path}"
            ),
        }

    media_type = _detected_media_type(path, data)
    if media_type is None:
        return {
            "error_code": "unsupported_image",
            "path": image_path,
            "message": (
                "Unsupported image type. Supported formats: png, jpeg, gif, webp, bmp, tiff."
            ),
        }

    relative_path = str(path.relative_to(support.ROOT)).replace("\\", "/")
    payload = base64.b64encode(data).decode("ascii")
    try:
        backend, result, model = _run_generalist_image_prompt(
            prompt=prompt_text,
            image_base64=payload,
            media_type=media_type,
            output_mode=mode,
        )
    except ValueError as exc:
        message = str(exc)
        if message == "No subagent LLM available":
            message = _image_backend_setup_hint()
        return {
            "status": "unavailable",
            "backend": runtime._backend(),
            "path": relative_path,
            "message": message,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "error_code": "backend_error",
            "backend": runtime._backend(),
            "path": relative_path,
            "message": loop._redact(str(exc)),
        }

    return {
        "status": "completed",
        "backend": backend,
        **({"model": model} if model else {}),
        "path": relative_path,
        "media_type": media_type,
        "output_mode": mode,
        "result": result.strip(),
    }


def register(mcp):
    """Register inspect_image on the FastMCP server."""
    runtime.configure_runtime(client_capabilities=None)
    return mcp.tool(
        description=describe(
            "Inspect an image with the generalist subagent profile. "
            "This tool accepts image_path, prompt, and optional output_mode, validates the workspace image file, "
            "sends the image as multimodal input to the active LLM backend, and returns the model output. "
            "When no LLM backend is available, the response uses status='unavailable'."
        )
    )(inspect_image)
