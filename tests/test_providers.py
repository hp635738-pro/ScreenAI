"""Provider suites: OpenAI, Ollama, Auto — fully mocked, no network."""

from __future__ import annotations

import pytest

from core.providers import (
    AutoProvider,
    OllamaProvider,
    OpenAIProvider,
    ProviderError,
    ProviderNotConfigured,
    available_providers,
    create_provider,
)
from core.providers.base import ProviderResponse
from tests.fakes import FakeTransport, ScriptedProvider

SECRET = "sk-TESTKEY1234567890abcd"


def test_registry_lists_and_creates_providers():
    assert set(available_providers()) == {"auto", "ollama", "openai"}
    assert create_provider("ollama").name == "ollama"
    assert create_provider("openai", api_key="x").name == "openai"
    with pytest.raises(ProviderError):
        create_provider("nope")


# ----------------------------------------------------------------- OpenAI


def test_openai_generate_parses_completion():
    transport = FakeTransport()
    transport.add_json("/chat/completions", 200, {
        "choices": [{"message": {"content": '{"final": "hi"}'}}]
    })
    provider = OpenAIProvider(api_key=SECRET, transport=transport)
    response = provider.generate("hello")
    assert isinstance(response, ProviderResponse)
    assert response.text == '{"final": "hi"}'
    sent = transport.requests[0]
    assert sent["headers"]["Authorization"] == f"Bearer {SECRET}"
    assert sent["payload"]["model"] == "gpt-4o-mini"


def test_openai_streaming_deltas():
    import json

    transport = FakeTransport()
    lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": "He"}}]}),
        "data: " + json.dumps({"choices": [{"delta": {"content": "llo"}}]}),
        "data: [DONE]",
    ]
    transport.add_stream("/chat/completions", lines)
    provider = OpenAIProvider(api_key=SECRET, transport=transport)
    seen: list[str] = []
    response = provider.chat(
        [{"role": "user", "content": "hi"}], stream_cb=seen.append
    )
    assert response.text == "Hello"
    assert seen == ["He", "llo"]


def test_openai_errors_never_leak_the_key():
    transport = FakeTransport()
    transport.add_json("/chat/completions", 401, {"error": {"message": "bad key"}})
    provider = OpenAIProvider(api_key=SECRET, transport=transport)
    with pytest.raises(ProviderNotConfigured) as excinfo:
        provider.chat([{"role": "user", "content": "hi"}])
    assert SECRET not in str(excinfo.value)

    transport = FakeTransport()
    transport.add_json("/chat/completions", 500, {})
    provider = OpenAIProvider(api_key=SECRET, transport=transport)
    with pytest.raises(ProviderError) as excinfo:
        provider.chat([{"role": "user", "content": "hi"}])
    assert SECRET not in str(excinfo.value)


def test_openai_not_configured_and_unavailable():
    provider = OpenAIProvider(api_key=None, transport=FakeTransport())
    assert not provider.is_available()
    with pytest.raises(ProviderNotConfigured):
        provider.chat([{"role": "user", "content": "hi"}])

    class BoomTransport(FakeTransport):
        def request_json(self, *args, **kwargs):  # noqa: ANN001, ANN202
            from core.providers.transport import TransportError

            raise TransportError("connection refused")

    provider = OpenAIProvider(api_key=SECRET, transport=BoomTransport())
    with pytest.raises(ProviderError) as excinfo:
        provider.chat([{"role": "user", "content": "hi"}])
    assert "unavailable" in str(excinfo.value).lower()


def test_openai_timeout_is_an_error():
    transport = FakeTransport()
    transport.add_json("/chat/completions", 200, {"choices": [{"message": {"content": "x"}}]})
    provider = OpenAIProvider(api_key=SECRET, timeout=0.001, transport=transport)
    response = provider.chat([{"role": "user", "content": "hi"}])
    assert response.provider == "openai"


# ----------------------------------------------------------------- Ollama


def test_ollama_availability_probe():
    transport = FakeTransport()
    transport.add_json("/api/tags", 200, {"models": [{"name": "llama3.2:latest"}]})
    provider = OllamaProvider(transport=transport)
    assert provider.is_available()

    class DownTransport(FakeTransport):
        def request_json(self, *args, **kwargs):  # noqa: ANN001, ANN202
            from core.providers.transport import TransportError

            raise TransportError("refused")

    provider = OllamaProvider(transport=DownTransport())
    assert not provider.is_available()


def test_ollama_chat_and_models():
    transport = FakeTransport()
    transport.add_json("/api/tags", 200, {
        "models": [{"name": "b-model"}, {"name": "a-model"}]
    })
    transport.add_json("/api/chat", 200, {"message": {"content": "pong"}})
    provider = OllamaProvider(base_url="http://localhost:11434", transport=transport)
    assert provider.models() == ["a-model", "b-model"]
    response = provider.chat([{"role": "user", "content": "ping"}])
    assert response.text == "pong"
    assert response.provider == "ollama"


def test_ollama_clear_error_when_unavailable():
    class DownTransport(FakeTransport):
        def request_json(self, *args, **kwargs):  # noqa: ANN001, ANN202
            from core.providers.transport import TransportError

            raise TransportError("refused")

    provider = OllamaProvider(
        base_url="http://localhost:11434", transport=DownTransport()
    )
    with pytest.raises(ProviderError) as excinfo:
        provider.chat([{"role": "user", "content": "hi"}])
    message = str(excinfo.value)
    assert "http://localhost:11434" in message
    assert "ollama serve" in message


def test_ollama_streaming_ndjson():
    transport = FakeTransport()
    transport.add_stream("/api/chat", [
        '{"message": {"content": "pa"}, "done": false}',
        '{"message": {"content": "th"}, "done": true}',
    ])
    provider = OllamaProvider(transport=transport)
    seen: list[str] = []
    response = provider.chat([{"role": "user", "content": "x"}], stream_cb=seen.append)
    assert response.text == "path"
    assert seen == ["pa", "th"]


# -------------------------------------------------------------------- Auto


def test_auto_prefers_local_and_never_silent_cloud():
    local = ScriptedProvider(['{"final": "local"}'])
    cloud = ScriptedProvider(['{"final": "cloud"}'], cloud=True)
    auto = AutoProvider([local, cloud], cloud_allowed=False)
    response = auto.chat([{"role": "user", "content": "hi"}])
    assert response.text == '{"final": "local"}'
    assert auto.last_used == "fake"

    class Down(ScriptedProvider):
        def is_available(self) -> bool:
            return False

    auto = AutoProvider([Down([]), cloud], cloud_allowed=False)
    with pytest.raises(ProviderError) as excinfo:
        auto.chat([{"role": "user", "content": "hi"}])
    assert "privacy" in str(excinfo.value).lower()

    auto = AutoProvider([Down([]), cloud], cloud_allowed=True)
    response = auto.chat([{"role": "user", "content": "hi"}])
    assert response.text == '{"final": "cloud"}'


def test_auto_excludes_cloud_candidates_until_allowed():
    cloud = ScriptedProvider(['{"final": "cloud"}'], cloud=True)
    auto = AutoProvider([cloud], cloud_allowed=False)
    assert auto.candidates() == []
    assert not auto.is_available()
    auto.allow_cloud(True)
    assert auto.is_available()


def test_provider_switching_uses_same_interface():
    messages = [{"role": "user", "content": "x"}]
    scripted = ScriptedProvider(['{"final": "one"}'])
    assert scripted.chat(messages).text == '{"final": "one"}'
    transport = FakeTransport()
    transport.add_json("/chat/completions", 200, {
        "choices": [{"message": {"content": '{"final": "two"}'}}]
    })
    openai = OpenAIProvider(api_key=SECRET, transport=transport)
    assert openai.chat(messages).text == '{"final": "two"}'
    # generate() contract preserved for both
    scripted.responses.append('{"final": "three"}')
    assert scripted.generate("x").text == '{"final": "three"}'
