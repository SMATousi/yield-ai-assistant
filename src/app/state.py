from __future__ import annotations

import dataclasses
from datetime import datetime

import requests

KNOWN_CLOUD_MODELS: list[str] = [
    "anthropic/claude-sonnet-4-6",
    "anthropic/claude-haiku-4-5-20251001",
    "anthropic/claude-opus-4-8",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
]


@dataclasses.dataclass
class SessionState:
    messages: list[dict]       # LiteLLM message history for multi-turn agent context
    chat_history: list[dict]   # Gradio chatbot format: [{"role": ..., "content": ...}]
    last_site: str | None


def make_session_state() -> SessionState:
    return SessionState(messages=[], chat_history=[], last_site=None)


def clear_session(state: SessionState) -> SessionState:
    return make_session_state()


def list_ollama_models(base_url: str = "http://localhost:11434") -> list[str]:
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=3)
        resp.raise_for_status()
        return sorted(m["name"] for m in resp.json().get("models", []))
    except Exception:
        return []


def doy_sort_key(plt_dtDoy: str) -> datetime:
    return datetime.strptime(plt_dtDoy, "%b-%d").replace(year=2000)
