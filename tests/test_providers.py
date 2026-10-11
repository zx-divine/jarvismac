import json
from types import SimpleNamespace as NS
import httpx
import pytest
from jarvis.config import Settings, ENDPOINTS
from jarvis.providers import Provider, ProviderError, anthropic_messages
from jarvis.gemini import GeminiProvider, contents_from_messages
from google.genai import types

def sse(events):
    return "".join("data: " + json.dumps(event) + "\n\n" for event in events).encode()

async def test_openai_streamed_text_tools_usage():
    events = [
        {"choices": [{"delta": {"content": "Ready, ASH."}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "system_info", "arguments": "{"}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "}"}}]}, "finish_reason": "tool_calls"}]},
        {"choices": [], "usage": {"total_tokens": 17}},
    ]
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, content=sse(events))
    pieces = []
    provider = Provider(Settings(provider="openai", endpoint=ENDPOINTS["openai"], model="test-model"), "fake-key", httpx.MockTransport(handle))
    reply = await provider.complete([{"role": "user", "content": "metrics"}], [], pieces.append)
    assert reply.text == "Ready, ASH." and reply.calls[0]["function"]["arguments"] == "{}"
    assert reply.usage["total_tokens"] == 17 and pieces == ["Ready, ASH."]
    assert requests[0].url.path == "/v1/chat/completions"

async def test_incomplete_stream_never_returns_tool():
    event = {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "power", "arguments": '{"action":"shutdown"}'}}]}}]}
    provider = Provider(Settings(model="test"), "fake", httpx.MockTransport(lambda request: httpx.Response(200, content=sse([event]))))
    with pytest.raises(ProviderError, match="before the response completed"):
        await provider.complete([], [], lambda _: None)

async def test_rate_limit_retry_and_secret_safe_error():
    attempts = []
    def handler(request):
        attempts.append(1)
        return httpx.Response(429, json={"error": "super-private-secret"})
    provider = Provider(Settings(model="test"), "fake", httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as error:
        await provider.complete([], [], lambda _: None)
    assert len(attempts) == 3 and "super-private-secret" not in str(error.value)

async def test_anthropic_stream_and_tool_results():
    events = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 5}}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello ASH"}},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "c1", "name": "system_info"}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{}"}},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 4}},
        {"type": "message_stop"},
    ]
    provider = Provider(Settings(provider="anthropic", endpoint=ENDPOINTS["anthropic"], model="test"), "fake", httpx.MockTransport(lambda r: httpx.Response(200, content=sse(events))))
    reply = await provider.complete([{"role": "system", "content": "Be Jarvis"}, {"role": "user", "content": "hi"}], [], lambda _: None)
    assert reply.text == "Hello ASH" and reply.calls[0]["id"] == "c1"
    converted = anthropic_messages([{"role": "assistant", "content": None, "tool_calls": reply.calls}, {"role": "tool", "tool_call_id": "c1", "content": "result"}])
    assert converted[1]["content"][0]["type"] == "tool_result"

async def test_missing_key_setup_guidance():
    for provider in (Provider(Settings(model="test"), ""), GeminiProvider(Settings(model="test"), "")):
        with pytest.raises(ProviderError, match="Settings"):
            await provider.complete([], [], lambda _: None)

class FakeModels:
    def __init__(self, chunks):
        self.chunks, self.config, self.contents = chunks, None, None
    async def generate_content_stream(self, model, contents, config):
        self.config, self.contents = config, contents
        async def stream():
            for chunk in self.chunks:
                yield chunk
        return stream()

class FakeClient:
    def __init__(self, chunks):
        self.models = FakeModels(chunks)
        async def close():
            pass
        self.aio = NS(models=self.models, aclose=close)
    def close(self):
        pass

async def test_native_gemini_tools_signatures_and_no_auto_execution():
    signed = types.Part(function_call=types.FunctionCall(name="system_info", args={}), thought_signature=b"signature")
    chunks = [types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text="Ready ASH"), signed]), finish_reason="STOP")], usage_metadata=types.GenerateContentResponseUsageMetadata(total_token_count=14))]
    client = FakeClient(chunks)
    provider = GeminiProvider(Settings(model="account-verified-model"), "fake", lambda key: client)
    messages = [{"role": "system", "content": "Be Jarvis"}, {"role": "user", "content": "metrics"}]
    reply = await provider.complete(messages, [], lambda _: None)
    assert reply.text == "Ready ASH" and reply.usage["total_tokens"] == 14
    assert client.models.config.automatic_function_calling.disable is True
    messages += [{"role": "assistant", "content": reply.text, "tool_calls": reply.calls, "_gemini_parts": reply.native_parts}, {"role": "tool", "tool_call_id": reply.calls[0]["id"], "content": '{"untrusted_tool_result":{"ok":true}}'}]
    converted = contents_from_messages(messages)
    assert converted[1].parts[1].thought_signature == b"signature"
    assert converted[2].parts[0].function_response.name == "system_info"

async def test_actual_google_sdk_serialization_and_model_discovery(monkeypatch):
    from google import genai
    from jarvis import gemini
    requests = []
    def transport(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"models": [{"name": "models/gemini-account-test", "supportedGenerationMethods": ["generateContent"]}]})
        payload = {"candidates": [{"content": {"role": "model", "parts": [{"text": "Hello ASH"}]}, "finishReason": "STOP"}], "usageMetadata": {"totalTokenCount": 8}}
        return httpx.Response(200, content=sse([payload]), headers={"content-type": "text/event-stream"})
    def factory(key):
        mock = httpx.MockTransport(transport)
        return genai.Client(api_key=key, http_options=types.HttpOptions(client_args={"transport": mock, "trust_env": False}, async_client_args={"transport": mock, "trust_env": False}))
    monkeypatch.setattr(gemini, "client_for", factory)
    assert await gemini.discover_models("dummy") == ["gemini-account-test"]
    provider = GeminiProvider(Settings(model="gemini-account-test"), "dummy", factory)
    schema = {"type": "function", "function": {"name": "system_info", "description": "metrics", "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}}}
    reply = await provider.complete([{"role": "system", "content": "Jarvis"}, {"role": "user", "content": "hello"}], [schema], lambda text: None)
    assert reply.text == "Hello ASH"
    body = json.loads(requests[-1].content)
    assert body["tools"][0]["functionDeclarations"][0]["name"] == "system_info"
    assert requests[-1].url.host == "generativelanguage.googleapis.com"
