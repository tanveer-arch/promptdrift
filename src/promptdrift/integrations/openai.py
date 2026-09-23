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
            try:
                result = await original_create(*args, **kwargs)
                _capture_result(recorder, kwargs, result, start, capture_kwargs)
                return result
            except Exception as e:
                raise e

        client.chat.completions.create = wrapped_create_async
    else:

        def wrapped_create_sync(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = original_create(*args, **kwargs)
                _capture_result(recorder, kwargs, result, start, capture_kwargs)
                return result
            except Exception as e:
                raise e

        client.chat.completions.create = wrapped_create_sync

    return client


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
