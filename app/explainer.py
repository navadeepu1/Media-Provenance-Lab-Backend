"""Strict, optional provider explanations with deterministic fallback and caching."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping

import httpx

from .config import settings
from .db import load_explanation_cache, save_explanation_cache

FORBIDDEN_VERDICT_TERMS = re.compile(r"\b(fake|real|authentic)\b", re.IGNORECASE)
NUMBER = re.compile(r"\b(?:\d+(?:\.\d+)?)\b")


def template_explanation(input_data: Mapping) -> str:
    signals = input_data.get("signals", [])
    sentences = [
        f"The evidence tier is {input_data.get('tier', 'INCONCLUSIVE')} under rule {input_data.get('rule_id', 'R3')}."
    ]
    for signal in signals:
        sentences.append(f"{signal['name']}: {signal['reason']}")
    limitations = input_data.get("limitations", [])
    if limitations:
        sentences.append("Limitations: " + " ".join(str(item) for item in limitations[:3]))
    return " ".join(sentences)[:1200]


def validate_explanation(text: str, input_data: Mapping) -> str | None:
    if not text or len(text.split()) > 120:
        return "The explanation must contain between one and 120 words."
    if FORBIDDEN_VERDICT_TERMS.search(text):
        return "The explanation contains a forbidden verdict term."
    rule_id = str(input_data.get("rule_id", ""))
    allowed_numbers = {rule_id, *NUMBER.findall(rule_id)}
    for signal in input_data.get("signals", []):
        if signal.get("score") is not None:
            allowed_numbers.add(str(signal["score"]))
    for number in NUMBER.findall(text):
        if number not in allowed_numbers:
            return f"The explanation contains an unapproved number: {number}."
    return None


def _cache_key(input_data: Mapping) -> str:
    canonical = json.dumps(input_data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(
        f"{settings.ai_provider}\0{canonical}".encode("utf-8")
    ).hexdigest()


def _prompt(input_data: Mapping) -> str:
    return (
        "Explain this media evidence report in plain English. Do not call the media "
        "fake, real, or authentic; do not introduce numbers; state uncertainty. "
        "Use at most 120 words.\n\n"
        + json.dumps(input_data, sort_keys=True, default=str)
    )


def _provider_candidate(input_data: Mapping) -> str | None:
    provider = settings.ai_provider.lower().strip()
    if provider == "none":
        return None
    if provider == "gemini":
        if not settings.gemini_api_key:
            return None
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.0-flash:generateContent"
        )
        response = httpx.post(
            url,
            params={"key": settings.gemini_api_key},
            json={"contents": [{"parts": [{"text": _prompt(input_data)}]}]},
            timeout=settings.explainer_timeout_seconds,
        )
        response.raise_for_status()
        parts = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
        return "".join(str(part.get("text", "")) for part in parts).strip() or None
    if provider == "groq":
        if not settings.groq_api_key:
            return None
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json={
                "model": "llama-3.1-8b-instant",
                "temperature": 0,
                "max_tokens": 180,
                "messages": [
                    {"role": "system", "content": "Return only the explanation text."},
                    {"role": "user", "content": _prompt(input_data)},
                ],
            },
            timeout=settings.explainer_timeout_seconds,
        )
        response.raise_for_status()
        return str(response.json().get("choices", [{}])[0].get("message", {}).get("content", "")).strip() or None
    raise ValueError(f"Unsupported explanation provider: {settings.ai_provider}")


def explain(input_data: Mapping, candidate: str | None = None) -> tuple[str, str]:
    key = _cache_key(input_data)
    cached = load_explanation_cache(key)
    if cached:
        return cached
    text = candidate
    source = "ai" if candidate else "template"
    if text is None:
        try:
            text = _provider_candidate(input_data)
            source = "ai" if text else "template"
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError,
                AttributeError, json.JSONDecodeError):
            text = None
            source = "template"
    text = text or template_explanation(input_data)
    if validate_explanation(text, input_data) is not None:
        text, source = template_explanation(input_data), "template"
    save_explanation_cache(key, text, source)
    return text, source
