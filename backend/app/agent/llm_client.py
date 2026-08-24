"""
Unified LLM Client.

Supports multiple providers via a consistent interface:
  - "mock"   : Offline template/rule-based engine (zero external API keys required)
  - "openai" : OpenAI Chat Completions API
  - "groq"   : Groq Cloud API (OpenAI-compatible)
  - "gemini" : Google Gemini API (via REST or OpenAI-compatible endpoint)
  - "ollama" : Local Ollama instance (e.g. http://localhost:11434/v1)

Configured via .env (LLM_PROVIDER, LLM_API_KEY, LLM_MODEL, LLM_BASE_URL, LLM_TEMPERATURE).
"""
import json
import logging
import re
from typing import Dict, Any, List, Optional

from backend.app.config.settings import settings

logger = logging.getLogger("app.llm")


class LLMClient:

    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.api_key = settings.LLM_API_KEY
        self.model = settings.LLM_MODEL
        self.base_url = settings.LLM_BASE_URL
        self.temperature = settings.LLM_TEMPERATURE

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: int = 2000,
    ) -> str:
        """Generate a text response from the configured LLM provider."""
        temp = temperature if temperature is not None else self.temperature

        if self.provider == "mock":
            return self._mock_generate(prompt, system_prompt)

        if self.provider in ("openai", "groq", "ollama", "gemini"):
            return self._call_openai_compatible(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temp,
                max_tokens=max_tokens,
            )

        return self._mock_generate(prompt, system_prompt)

    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = 0.0,
    ) -> Dict[str, Any]:
        """
        Generate structured JSON from the configured LLM provider.
        Extracts JSON block if surrounded by ```json ... ``` markdown.
        """
        sys_prompt = (system_prompt or "") + "\nYou MUST respond ONLY with valid, parseable JSON."
        raw_text = self.generate_text(prompt, system_prompt=sys_prompt.strip(), temperature=temperature)

        # Extract JSON from code blocks if present
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text)
        candidate = json_match.group(1).strip() if json_match else raw_text.strip()

        try:
            return json.loads(candidate)
        except Exception as e:
            logger.warning("Failed to parse JSON from LLM response: %s", e)
            # Try to find first { and last }
            first_brace = candidate.find("{")
            last_brace = candidate.rfind("}")
            if first_brace != -1 and last_brace != -1:
                try:
                    return json.loads(candidate[first_brace:last_brace + 1])
                except Exception:
                    pass
            return {"raw_text": raw_text, "error": "JSON parse failed"}

    # -----------------------------------------------------------------------
    # Provider Implementations
    # -----------------------------------------------------------------------

    def _call_openai_compatible(
        self,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> str:
        import httpx

        # Determine endpoint URL and default model
        base_url = self.base_url
        model = self.model

        if self.provider == "openai":
            base_url = base_url or "https://api.openai.com/v1"
            model = model if model and model != "default" else "gpt-4o-mini"
        elif self.provider == "groq":
            base_url = base_url or "https://api.groq.com/openai/v1"
            model = model if model and model != "default" else "llama-3.1-70b-versatile"
        elif self.provider == "ollama":
            base_url = base_url or "http://localhost:11434/v1"
            model = model if model and model != "default" else "llama3.2"
        elif self.provider == "gemini":
            base_url = base_url or "https://generativelanguage.googleapis.com/v1beta/openai"
            model = model if model and model != "default" else "gemini-1.5-flash"

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        resp = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def _mock_generate(self, prompt: str, system_prompt: Optional[str]) -> str:
        """Deterministic offline mock responses."""
        prompt_lower = prompt.lower()

        if "plan" in prompt_lower or "question" in prompt_lower:
            return json.dumps({
                "questions": [
                    "What is the core definition and purpose?",
                    "What are the primary architectural components?",
                    "How does it integrate with existing workflows?",
                ],
                "search_queries": [
                    "overview and architecture tutorial",
                    "key concepts and examples",
                    "best practices and comparison",
                ]
            })

        if "verify" in prompt_lower or "claim" in prompt_lower:
            return json.dumps({
                "verification_status": "supported",
                "confidence": 0.88,
                "reasoning": "Evidence across multiple sources consistently supports the core proposition.",
                "contradictions": [],
            })

        if "synthesize" in prompt_lower or "proposal" in prompt_lower:
            return (
                "# Structured Knowledge Synthesis\n\n"
                "## Executive Summary\n"
                "The researched domain provides high-impact capabilities for knowledge grounding.\n\n"
                "## Key Findings\n"
                "1. Fundamental architecture relies on modular components with well-defined contracts.\n"
                "2. Verification mechanisms ensure factual consistency and minimize hallucinations.\n\n"
                "## Relationships\n"
                "- `ConceptA` --[enhances]--> `ConceptB`\n"
            )

        return f"Mock response answering: {prompt[:100]}..."


llm_client = LLMClient()
