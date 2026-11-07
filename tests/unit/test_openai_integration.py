"""Tests for OpenAI client integration."""

from __future__ import annotations

import sys
from unittest.mock import Mock

import pytest

from promptdrift.capture.recorder import CaptureRecorder


class MockMessage:
    def __init__(self, content):
        self.content = content


class MockChoice:
    def __init__(self, content):
        self.message = MockMessage(content)


class MockUsage:
    def __init__(self, prompt, comp):
        self.prompt_tokens = prompt
        self.completion_tokens = comp


class MockResult:
    def __init__(self, content, model="gpt-3.5-turbo"):
        self.choices = [MockChoice(content)]
        self.model = model
        self.usage = MockUsage(10, 20)


class MockDelta:
    def __init__(self, content):
        self.content = content


class MockStreamChoice:
    def __init__(self, content):
        self.delta = MockDelta(content)


class MockStreamChunk:
    def __init__(self, content, model="gpt-4"):
        self.choices = [MockStreamChoice(content)]
        self.model = model
        self.usage = None


class MockCompletions:
    def create(self, **kwargs):
        return MockResult("Hello back!", kwargs.get("model", "default-model"))

    async def create_async(self, **kwargs):
        return MockResult("Async hello!", kwargs.get("model", "default-model"))


class MockChat:
    def __init__(self, is_async=False):
        self.completions = MockCompletions()
        if is_async:
            self.completions.create = self.completions.create_async


class MockOpenAI:
    def __init__(self, is_async=False):
        self.chat = MockChat(is_async)


@pytest.fixture
def recorder():
    return CaptureRecorder()


def test_wrap_openai_sync(recorder, monkeypatch):
    from promptdrift.integrations.openai import wrap_openai

    class FakeOpenAIModule:
        AsyncOpenAI = type("AsyncOpenAI", (object,), {})

    monkeypatch.setitem(sys.modules, "openai", FakeOpenAIModule())

    client = MockOpenAI()
    wrapped = wrap_openai(client, recorder, prompt="test_prompt")

    res = wrapped.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a bot."},
            {"role": "user", "content": "Hi there!"},
        ],
    )

    assert res.choices[0].message.content == "Hello back!"


@pytest.mark.anyio
async def test_wrap_openai_async(recorder, monkeypatch):
    from promptdrift.integrations.openai import wrap_openai

    class FakeAsyncOpenAI(MockOpenAI):
        pass

    class FakeOpenAIModule:
        AsyncOpenAI = FakeAsyncOpenAI

    monkeypatch.setitem(sys.modules, "openai", FakeOpenAIModule())

    client = FakeAsyncOpenAI(is_async=True)
    wrapped = wrap_openai(client, recorder, prompt="test_async")

    res = await wrapped.chat.completions.create(
        model="gpt-3.5", messages=[{"role": "user", "content": "async msg"}]
    )

    assert res.choices[0].message.content == "Async hello!"


def test_wrap_openai_sync_stream(recorder, monkeypatch):
    from promptdrift.integrations.openai import wrap_openai

    class FakeOpenAIModule:
        AsyncOpenAI = type("AsyncOpenAI", (object,), {})

    monkeypatch.setitem(sys.modules, "openai", FakeOpenAIModule())
    recorder.record = Mock()

    chunks = [
        MockStreamChunk("Hello "),
        MockStreamChunk("world!"),
    ]

    client = MockOpenAI()
    client.chat.completions.create = lambda **kwargs: iter(chunks)

    wrapped = wrap_openai(client, recorder, prompt="stream_test")

    stream = wrapped.chat.completions.create(
        model="gpt-4",
        stream=True,
        messages=[{"role": "user", "content": "Say hello"}],
    )

    received_chunks = list(stream)

    assert received_chunks == chunks
    recorder.record.assert_called_once()

    recorded_data = recorder.record.call_args.kwargs
    assert recorded_data["output"] == "Hello world!"
    assert recorded_data["model"] == "gpt-4"
    assert recorded_data["provider"] == "openai"


@pytest.mark.anyio
async def test_wrap_openai_async_stream(recorder, monkeypatch):
    from promptdrift.integrations.openai import wrap_openai

    class FakeAsyncOpenAI(MockOpenAI):
        pass

    class FakeOpenAIModule:
        AsyncOpenAI = FakeAsyncOpenAI

    monkeypatch.setitem(sys.modules, "openai", FakeOpenAIModule())
    recorder.record = Mock()

    chunks = [
        MockStreamChunk("Async "),
        MockStreamChunk("stream!"),
    ]

    async def mock_stream():
        for chunk in chunks:
            yield chunk

    async def mock_create(**kwargs):
        return mock_stream()

    client = FakeAsyncOpenAI(is_async=True)
    client.chat.completions.create = mock_create

    wrapped = wrap_openai(client, recorder, prompt="async_stream_test")

    stream = await wrapped.chat.completions.create(
        model="gpt-4",
        stream=True,
        messages=[{"role": "user", "content": "Say hello"}],
    )

    received_chunks = [chunk async for chunk in stream]

    assert received_chunks == chunks
    recorder.record.assert_called_once()

    recorded_data = recorder.record.call_args.kwargs
    assert recorded_data["output"] == "Async stream!"
    assert recorded_data["model"] == "gpt-4"
    assert recorded_data["provider"] == "openai"


def test_wrap_openai_sync_stream_interrupted(recorder, monkeypatch):
    from promptdrift.integrations.openai import wrap_openai

    class FakeOpenAIModule:
        AsyncOpenAI = type("AsyncOpenAI", (object,), {})

    monkeypatch.setitem(sys.modules, "openai", FakeOpenAIModule())
    recorder.record = Mock()

    def mock_stream():
        yield MockStreamChunk("Partial ")
        raise RuntimeError("Stream interrupted")

    client = MockOpenAI()
    client.chat.completions.create = lambda **kwargs: mock_stream()

    wrapped = wrap_openai(client, recorder)

    stream = wrapped.chat.completions.create(
        model="gpt-4",
        stream=True,
        messages=[{"role": "user", "content": "Test"}],
    )

    with pytest.raises(RuntimeError, match="Stream interrupted"):
        list(stream)

    recorder.record.assert_called_once()
    assert recorder.record.call_args.kwargs["output"] == "Partial "


@pytest.mark.anyio
async def test_wrap_openai_async_stream_interrupted(recorder, monkeypatch):
    from promptdrift.integrations.openai import wrap_openai

    class FakeAsyncOpenAI(MockOpenAI):
        pass

    class FakeOpenAIModule:
        AsyncOpenAI = FakeAsyncOpenAI

    monkeypatch.setitem(sys.modules, "openai", FakeOpenAIModule())
    recorder.record = Mock()

    async def mock_stream():
        yield MockStreamChunk("Partial async ")
        raise RuntimeError("Async stream interrupted")

    async def mock_create(**kwargs):
        return mock_stream()

    client = FakeAsyncOpenAI(is_async=True)
    client.chat.completions.create = mock_create

    wrapped = wrap_openai(client, recorder)

    stream = await wrapped.chat.completions.create(
        model="gpt-4",
        stream=True,
        messages=[{"role": "user", "content": "Test"}],
    )

    with pytest.raises(RuntimeError, match="Async stream interrupted"):
        async for _ in stream:
            pass

    recorder.record.assert_called_once()
    assert recorder.record.call_args.kwargs["output"] == "Partial async "
