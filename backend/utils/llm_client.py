from __future__ import annotations

from typing import Any

import json
import re

from langchain_core.messages import HumanMessage

from agents.llm import get_llm


def generate_text_with_nvidia_llama(prompt: str, temperature: float = 0.2) -> str:
    llm = get_llm(temperature=temperature)
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content


def extract_json_text(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def parse_json_payload(text: str) -> Any:
    cleaned = extract_json_text(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}|\[.*\]", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))

