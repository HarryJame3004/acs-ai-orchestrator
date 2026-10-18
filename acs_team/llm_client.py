import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional
from .config import ROUTER_BASE_URL, ROUTER_API_KEY, MODEL_FALLBACK
from .resilience import CircuitBreaker, FailureKind, RetryPolicy, classify
import time
import urllib.error

_CIRCUIT = CircuitBreaker()

logger = logging.getLogger("acs_team.llm")


def clean_response_text(raw_text: str) -> str:
    """Strip SSE data:[DONE] markers and extra trailing junk from 9Router."""
    text = raw_text.strip()
    if "data: [DONE]" in text:
        text = text.split("data: [DONE]")[0].strip()
    return text


def query_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: str = "free-reasoning",
    temperature: float = 0.2,
    timeout: int = 90,
    retries: int = 2,
) -> str:
    """Send a chat completion request to 9Router with retries and failover."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    models_to_try = [model]
    if MODEL_FALLBACK not in models_to_try:
        models_to_try.append(MODEL_FALLBACK)
    if "free-light" not in models_to_try:
        models_to_try.append("free-light")

    last_error = None
    for attempt_model in models_to_try:
        for attempt in range(retries + 1):
            if not _CIRCUIT.allow():
                raise RuntimeError("Model gateway circuit is open; wait for cooldown or correct configuration")
            try:
                payload = json.dumps(
                    {
                        "model": attempt_model,
                        "messages": messages,
                        "temperature": temperature,
                    }
                ).encode("utf-8")

                req = urllib.request.Request(
                    f"{ROUTER_BASE_URL}/chat/completions",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {ROUTER_API_KEY}",
                    },
                )

                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read().decode("utf-8")
                    cleaned = clean_response_text(raw)
                    data = json.loads(cleaned)
                    choice = data["choices"][0]["message"]
                    content = choice.get("content") or ""
                    # If content is empty but reasoning is present
                    if not content and choice.get("reasoning"):
                        content = choice["reasoning"]
                    _CIRCUIT.success()
                    return content
            except Exception as e:
                last_error = e
                kind = classify(e.code if isinstance(e, urllib.error.HTTPError) else None, e)
                _CIRCUIT.failure(kind)
                if kind in {FailureKind.AUTH, FailureKind.PERMANENT, FailureKind.UNKNOWN}:
                    raise RuntimeError(f"Model gateway failed: {kind.value}; no automatic credential retry") from None
                if attempt < retries:
                    time.sleep(RetryPolicy().delay(attempt))
                logger.warning(
                    f"Model {attempt_model} attempt {attempt + 1} failed: {e}"
                )

    raise RuntimeError(
        f"All model attempts failed for query. Last error: {last_error}"
    )


def extract_json_block(text: str) -> Dict[str, Any]:
    """Extract and parse JSON object from markdown code fences or raw text."""
    # Strip <think>...</think> blocks if present from reasoning models
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Try finding fenced json: ```json { ... } ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding outermost braces { ... }
    match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Fallback: parse entire string
    return json.loads(cleaned.strip())

