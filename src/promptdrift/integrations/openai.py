"""OpenAI integration for PromptDrift CaptureRecorder."""

from __future__ import annotations

import time
from typing import Any

from promptdrift.capture.recorder import CaptureRecorder


def wrap_openai(client: Any, recorder: CaptureRecorder, **capture_kwargs: Any) -> Any:
    """Wrap an OpenAI client (sync or async) to capture interactions.

    Args:
        client: The OpenAI client instance (e.g. openai.OpenAI or openai.AsyncOpenAI)
        recorder: The CaptureRecorder instance
        **capture_kwargs: Additional tags or default kwargs for capture

    Returns:
        The wrapped client.
    """
    try:
        import openai
    except ImportError as e:
        raise ImportError("OpenAI integration requires the 'openai' package.") from e

    is_async = isinstance(client, openai.AsyncOpenAI)

    original_create = client.chat.completions.create

    if is_async:

        async def wrapped_create_async(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            result = await original_create(*args, **kwargs)

            if kwargs.get("stream", False):
                return _wrap_async_stream(result, recorder, kwargs, start, capture_kwargs)

            _capture_result(recorder, kwargs, result, start, capture_kwargs)
            return result

        client.chat.completions.create = wrapped_create_async

    else:

        def wrapped_create_sync(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            result = original_create(*args, **kwargs)

            if kwargs.get("stream", False):
                return _wrap_sync_stream(result, recorder, kwargs, start, capture_kwargs)

            _capture_result(recorder, kwargs, result, start, capture_kwargs)
            return result

        client.chat.completions.create = wrapped_create_sync

    return client


def _wrap_sync_stream(
    stream: Any,
    recorder: CaptureRecorder,
    kwargs: dict[str, Any],
    start_time: float,
    capture_kwargs: dict[str, Any],
):
    """Capture text from a synchronous stream while yielding chunks."""
    output_parts = []
    model = kwargs.get("model", "unknown")
    usage = None

    try:
        for chunk in stream:
            model = getattr(chunk, "model", None) or model
            usage = getattr(chunk, "usage", None) or usage

            for choice in getattr(chunk, "choices", None) or []:
                delta = getattr(choice, "delta", None)
                content = getattr(delta, "content", None)

                if isinstance(content, str):
                    output_parts.append(content)

            yield chunk
    finally:
        _capture_stream_result(
            recorder,
            kwargs,
            "".join(output_parts),
            model,
            usage,
            start_time,
            capture_kwargs,
        )


async def _wrap_async_stream(
    stream: Any,
    recorder: CaptureRecorder,
    kwargs: dict[str, Any],
    start_time: float,
    capture_kwargs: dict[str, Any],
):
    """Capture text from an asynchronous stream while yielding chunks."""
    output_parts = []
    model = kwargs.get("model", "unknown")
    usage = None

    try:
        async for chunk in stream:
            model = getattr(chunk, "model", None) or model
            usage = getattr(chunk, "usage", None) or usage

            for choice in getattr(chunk, "choices", None) or []:
                delta = getattr(choice, "delta", None)
                content = getattr(delta, "content", None)

                if isinstance(content, str):
                    output_parts.append(content)

            yield chunk
    finally:
        _capture_stream_result(
            recorder,
            kwargs,
            "".join(output_parts),
            model,
            usage,
            start_time,
            capture_kwargs,
        )


def _capture_stream_result(
    recorder: CaptureRecorder,
    kwargs: dict[str, Any],
    output: str,
    model: str,
    usage: Any,
    start_time: float,
    capture_kwargs: dict[str, Any],
) -> None:
    """Capture completed or partially received streaming output safely."""
    try:
        latency_ms = (time.perf_counter() - start_time) * 1000

        messages = kwargs.get("messages", [])
        system_prompt = next(
            (m.get("content") for m in messages if m.get("role") == "system"), None
        )

        user_messages = [m.get("content") for m in messages if m.get("role") == "user"]
        input_text = "\n".join(filter(None, user_messages))

        input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage else None

        recorder.record(
            prompt=capture_kwargs.get("prompt", "openai_chat"),
            input_text=input_text,
            output=output,
            model=model,
            provider="openai",
            system_prompt=system_prompt,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tags=capture_kwargs.get("tags"),
            variables=capture_kwargs.get("variables"),
        )
    except Exception:
        pass


def _capture_result(
    recorder: CaptureRecorder,
    kwargs: dict[str, Any],
    result: Any,
    start_time: float,
    capture_kwargs: dict[str, Any],
) -> None:
    """Internal helper to capture a result without crashing."""
    try:
        latency_ms = (time.perf_counter() - start_time) * 1000

        messages = kwargs.get("messages", [])
        system_prompt = next(
            (m.get("content") for m in messages if m.get("role") == "system"), None
        )

        user_messages = [m.get("content") for m in messages if m.get("role") == "user"]
        input_text = "\n".join(filter(None, user_messages))

        output = ""
        if hasattr(result, "choices") and result.choices:
            output = result.choices[0].message.content or ""

        model = getattr(result, "model", kwargs.get("model", "unknown"))

        usage = getattr(result, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage else None

        # Estimate cost roughly if possible, but keep simple

        recorder.record(
            prompt=capture_kwargs.get("prompt", "openai_chat"),
            input_text=input_text,
            output=output,
            model=model,
            provider="openai",
            system_prompt=system_prompt,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tags=capture_kwargs.get("tags"),
            variables=capture_kwargs.get("variables"),
        )
    except Exception:
        pass
