from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.llm import get_llm


def call_llm_json(prompt: str, temperature: float = 0.2) -> str:
    """Call the configured NVIDIA chat model and return the raw text response."""
    llm = get_llm(temperature=temperature)
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content
