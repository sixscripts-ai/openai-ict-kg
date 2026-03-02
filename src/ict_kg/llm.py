"""LLM client abstraction for Gemini (primary) and Ollama (fallback).

Usage:
    client = get_llm_client()
    response = client.complete("Your prompt here")
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Protocol


class LLMClient(Protocol):
    name: str

    def complete(self, prompt: str) -> str:
        """Return the text completion for the given prompt."""
        ...


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

@dataclass
class GeminiLLMClient:
    name: str = "gemini"
    model: str = "gemini-2.0-flash"
    api_key: str = field(default="")

    def __post_init__(self) -> None:
        if not self.api_key:
            self.api_key = os.getenv("GEMINI_API_KEY", "")

    def complete(self, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        import httpx
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 2048},
        }
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

@dataclass
class OllamaLLMClient:
    name: str = "ollama"
    model: str = "llama3"
    base_url: str = "http://127.0.0.1:11434"

    def complete(self, prompt: str) -> str:
        import httpx
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
            )
            r.raise_for_status()
        return r.json().get("response", "")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_llm_client() -> LLMClient:
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    if provider == "ollama":
        return OllamaLLMClient(
            model=os.getenv("OLLAMA_LLM_MODEL", "llama3"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        )
    return GeminiLLMClient(
        model=os.getenv("GEMINI_LLM_MODEL", "gemini-2.0-flash"),
        api_key=os.getenv("GEMINI_API_KEY", ""),
    )


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------

def extract_json_list(text: str) -> list:
    """Extract the first JSON array from an LLM response string."""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
