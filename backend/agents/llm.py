from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from utils.config import settings


NVIDIA_CHAT_COMPLETIONS_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


@dataclass
class LLMResponse:
    content: str


@dataclass
class LLMChunk:
    content: str


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text", "")))
            else:
                parts.append(str(part))
        return "".join(parts)
    return str(content)


def _message_to_payload(message: BaseMessage) -> dict[str, str]:
    if isinstance(message, SystemMessage):
        role = "system"
    elif isinstance(message, HumanMessage):
        role = "user"
    elif isinstance(message, AIMessage):
        role = "assistant"
    else:
        role = "user"

    return {"role": role, "content": _content_to_text(message.content)}


class NVIDIAChatClient:
    """Minimal OpenAI-compatible NVIDIA chat client used by the backend agents."""

    def __init__(self, model: str, api_key: str, temperature: float = 0.2) -> None:
        self.model = model
        self.api_key = api_key
        self.temperature = temperature

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, messages: Iterable[BaseMessage], *, stream: bool) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [_message_to_payload(message) for message in messages],
            "temperature": self.temperature,
            "stream": stream,
        }

    def invoke(self, messages: Iterable[BaseMessage]) -> LLMResponse:
        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY is not set in the environment.")

        payload = self._payload(messages, stream=False)
        with httpx.Client(timeout=15.0) as client:
            response = client.post(NVIDIA_CHAT_COMPLETIONS_URL, json=payload, headers=self.headers)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"].get("content", "")
        return LLMResponse(content=content)

    async def astream(self, messages: Iterable[BaseMessage]):
        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY is not set in the environment.")

        payload = self._payload(messages, stream=True)
        async with httpx.AsyncClient(timeout=15.0) as client:
            async with client.stream(
                "POST",
                NVIDIA_CHAT_COMPLETIONS_URL,
                json=payload,
                headers=self.headers,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = line.removeprefix("data:").strip()
                    if not chunk or chunk == "[DONE]":
                        if chunk == "[DONE]":
                            break
                        continue
                    try:
                        data = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    token = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if token:
                        yield LLMChunk(content=token)


def get_llm(temperature: float = 0.2) -> NVIDIAChatClient:
    if not settings.nvidia_api_key:
        raise ValueError("NVIDIA_API_KEY is not set in the environment.")

    return NVIDIAChatClient(
        model=settings.nvidia_model,
        api_key=settings.nvidia_api_key,
        temperature=temperature,
    )
