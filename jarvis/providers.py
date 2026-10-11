"""Small REST provider adapters with bounded SSE parsing and real tool calls."""
import asyncio
from dataclasses import dataclass, field
import json
from typing import Callable
import httpx
from .config import Settings

class ProviderError(RuntimeError):
    pass

@dataclass
class Reply:
    text: str = ""
    calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)

async def events(response):
    lines = []
    size = 0
    async for line in response.aiter_lines():
        size += len(line)
        if size > 4_000_000:
            raise ProviderError("Provider response exceeded the safety limit.")
        if not line:
            if lines:
                payload = "\n".join(lines)
                lines.clear()
                if payload == "[DONE]":
                    return
                yield json.loads(payload)
        elif line.startswith("data:"):
            lines.append(line[5:].lstrip())
    if lines and "\n".join(lines) != "[DONE]":
        yield json.loads("\n".join(lines))

def anthropic_messages(messages):
    result = []
    for msg in messages:
        role = msg["role"]
        if role == "system":
            continue
        if role == "tool":
            role = "user"
            blocks = [{"type": "tool_result", "tool_use_id": msg["tool_call_id"], "content": msg["content"]}]
        else:
            blocks = []
            if msg.get("content"):
                blocks.append({"type": "text", "text": msg["content"]})
            for call in msg.get("tool_calls", []):
                fn = call["function"]
                blocks.append({"type": "tool_use", "id": call["id"], "name": fn["name"], "input": json.loads(fn["arguments"])})
        if not blocks:
            continue
        if result and result[-1]["role"] == role:
            result[-1]["content"].extend(blocks)
        else:
            result.append({"role": role, "content": blocks})
    return result

class Provider:
    def __init__(self, settings: Settings, key: str, transport=None):
        self.settings, self.key, self.transport = settings, key, transport

    async def complete(self, messages, tools, on_text: Callable[[str], None]) -> Reply:
        if not self.key:
            raise ProviderError("ASH, open Settings, choose a provider and model, then save its API key. API billing is separate from chat subscriptions.")
        if not self.settings.model.strip():
            raise ProviderError("Choose an available model ID in Settings. Model access depends on your API account.")
        is_claude = self.settings.provider == "anthropic"
        if is_claude:
            path = "/messages"
            headers = {"x-api-key": self.key, "anthropic-version": "2023-06-01"}
            body = {"model": self.settings.model, "max_tokens": 2048, "stream": True,
                    "system": messages[0]["content"], "messages": anthropic_messages(messages)}
            if tools:
                body["tools"] = [{"name": t["function"]["name"], "description": t["function"]["description"], "input_schema": t["function"]["parameters"]} for t in tools]
        else:
            path = "/chat/completions"
            headers = {"Authorization": "Bearer " + self.key}
            body = {"model": self.settings.model, "messages": messages, "stream": True,
                    "stream_options": {"include_usage": True}}
            if tools:
                body["tools"] = tools
        # Never follow redirects with credentials; ignore proxy environment variables.
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=15), follow_redirects=False, trust_env=False, transport=self.transport) as client:
            for attempt in range(3):
                reply = Reply()
                emitted = False
                try:
                    async with client.stream("POST", self.settings.endpoint + path, headers=headers, json=body) as response:
                        if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                            await asyncio.sleep(0.5 * 2 ** attempt)
                            continue
                        if response.status_code != 200:
                            # Error bodies can echo user prompts or API keys; do not expose them.
                            reason = {401: "Credential rejected. Update the API key in Settings.", 403: "Your API account cannot access this resource.", 404: "Model or endpoint not found. Check Settings.", 429: "Provider quota or rate limit reached. Check API billing."}.get(response.status_code, "Check provider availability and Settings.")
                            raise ProviderError(f"API returned HTTP {response.status_code}. {reason}")
                        calls = {}
                        finished = False
                        async for event in events(response):
                            if is_claude:
                                etype = event.get("type")
                                if etype == "error":
                                    raise ProviderError("Provider reported a streaming error. Please retry.")
                                if etype == "message_start":
                                    reply.usage.update(event.get("message", {}).get("usage", {}))
                                elif etype == "content_block_start":
                                    block = event["content_block"]
                                    if block["type"] == "tool_use":
                                        calls[event["index"]] = {"id": block["id"], "type": "function", "function": {"name": block["name"], "arguments": ""}}
                                elif etype == "content_block_delta":
                                    delta = event["delta"]
                                    if delta["type"] == "text_delta":
                                        piece = delta["text"]
                                        emitted = True
                                        reply.text += piece
                                        on_text(piece)
                                    elif delta["type"] == "input_json_delta":
                                        calls[event["index"]]["function"]["arguments"] += delta["partial_json"]
                                elif etype == "message_delta":
                                    reply.usage.update(event.get("usage", {}))
                                    if event.get("delta", {}).get("stop_reason") in {"max_tokens", "pause_turn"}:
                                        raise ProviderError("Response was truncated; no pending actions were executed. Ask a shorter question.")
                                elif etype == "message_stop":
                                    finished = True
                            else:
                                if event.get("error"):
                                    raise ProviderError("Provider reported a streaming error. Please retry.")
                                if event.get("usage"):
                                    reply.usage.update(event["usage"])
                                for choice in event.get("choices", []):
                                    if choice.get("finish_reason") in {"length", "content_filter"}:
                                        raise ProviderError("Response was truncated or filtered; no pending actions were executed.")
                                    if choice.get("finish_reason"):
                                        finished = True
                                    delta = choice.get("delta", {})
                                    if delta.get("content"):
                                        piece = delta["content"]
                                        emitted = True
                                        reply.text += piece
                                        on_text(piece)
                                    for fragment in delta.get("tool_calls", []):
                                        index = fragment["index"]
                                        call = calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                                        call["id"] += fragment.get("id", "")
                                        for key in ("name", "arguments"):
                                            call["function"][key] += fragment.get("function", {}).get(key, "")
                        if not finished:
                            raise ProviderError("Connection ended before the response completed. Pending actions were not executed.")
                        reply.calls = [calls[i] for i in sorted(calls)]
                        if len(reply.calls) > 8 or any(not c["id"] or not c["function"]["name"] for c in reply.calls):
                            raise ProviderError("Invalid or excessive tool calls from provider.")
                        for call in reply.calls:
                            json.loads(call["function"]["arguments"] or "{}")
                        return reply
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if emitted or attempt == 2:
                        raise ProviderError("Network request failed or timed out. Local quick commands remain available.") from exc
                    await asyncio.sleep(0.5 * 2 ** attempt)
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise ProviderError("Provider returned an invalid streaming response. Check model tool support.") from exc
        raise ProviderError("Provider unavailable after retries.")
