"""Tests for OpenAI client integration."""

from __future__ import annotations

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
    import sys

    from promptdrift.integrations.openai import wrap_openai

    # Mock openai module
    class FakeOpenAIModule:
        AsyncOpenAI = type("AsyncOpenAI", (object,), {})

    monkeypatch.setitem(sys.modules, "openai", FakeOpenAIModule())

    client = MockOpenAI()
    wrapped = wrap_openai(client, recorder, prompt="test_prompt")

    # Trigger a sync call
    res = wrapped.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a bot."},
            {"role": "user", "content": "Hi there!"},
        ],
    )

    assert res.choices[0].message.content == "Hello back!"

    # We can't directly check the DB without sqlite setup, but we know _capture_result didn't crash.
    # The record should have been called on recorder.


@pytest.mark.anyio
async def test_wrap_openai_async(recorder, monkeypatch):
    import sys

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
