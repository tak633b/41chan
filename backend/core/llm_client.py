"""
41chan LLM Client
Supports ZAI / Ollama / OpenRouter backends.
Switch via ORACLE_LLM_BACKEND env var (zai / ollama / openrouter).
"""

import json
import os
import re
import time
import random
import requests
from typing import List, Dict, Any, Optional
from openai import OpenAI


import threading

# ZAI time-slot parallelization (2-slot alternating for effective 1.5s interval)
_ZAI_SLOTS = [
    {"lock": threading.Lock(), "last_call": 0.0},
    {"lock": threading.Lock(), "last_call": 0.0},
]
_ZAI_SLOT_SELECTOR_LOCK = threading.Lock()  # Ensures atomic slot selection


class OracleLLMClient:
    """LLM client (ZAI / Ollama / OpenRouter switchable, with retry)"""

    # ZAI settings
    ZAI_API_KEY = os.environ.get("ORACLE_ZAI_API_KEY", "")
    ZAI_BASE_URL = "https://api.z.ai/api/coding/paas/v4"
    ZAI_MODEL = os.environ.get("ORACLE_ZAI_MODEL", "glm-4.7")

    # Ollama settings
    OLLAMA_API_URL = "http://localhost:11434/api/chat"
    OLLAMA_MODEL = os.environ.get("ORACLE_OLLAMA_MODEL", "qwen3.5:9b")

    # OpenRouter settings
    OPENROUTER_API_KEY = os.environ.get(
        "OPENROUTER_API_KEY",
        "***REDACTED_OPENROUTER***",
    )
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL = os.environ.get(
        "OPENROUTER_MODEL",
        "nvidia/nemotron-3-super-120b-a12b:free",
    )

    MIN_CALL_INTERVAL = 3.0  # For ZAI
    OLLAMA_CALL_INTERVAL = 0.1  # Local model — minimal interval
    OPENROUTER_CALL_INTERVAL = 1.0  # Free tier — be conservative

    def __init__(self, backend: Optional[str] = None, model: Optional[str] = None):
        self.backend = backend or os.environ.get("ORACLE_LLM_BACKEND", "zai")

        if self.backend == "zai":
            self.client = OpenAI(
                api_key=self.ZAI_API_KEY,
                base_url=self.ZAI_BASE_URL,
                max_retries=0,
                timeout=90.0,
            )
            self.model = self.ZAI_MODEL
            self._interval = self.MIN_CALL_INTERVAL
        elif self.backend == "openrouter":
            self.client = OpenAI(
                api_key=self.OPENROUTER_API_KEY,
                base_url=self.OPENROUTER_BASE_URL,
                max_retries=0,
                timeout=120.0,
            )
            self.model = os.environ.get("OPENROUTER_MODEL", self.OPENROUTER_MODEL)
            self._interval = self.OPENROUTER_CALL_INTERVAL
        else:
            self.client = None  # Ollama uses requests directly
            self.model = model or os.environ.get("ORACLE_OLLAMA_MODEL", self.OLLAMA_MODEL)
            self._interval = self.OLLAMA_CALL_INTERVAL

        self._last_call_time = 0.0
        print(f"[OracleLLM] Backend: {self.backend} | Model: {self.model}")

    def _call_ollama(self, messages: List[Dict[str, str]], temperature: float, num_predict: int = 8192) -> str:
        """Direct Ollama native API call"""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
            },
        }
        resp = requests.post(self.OLLAMA_API_URL, json=payload, timeout=600)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("message", {}).get("content", "")
        if not content:
            raise ValueError("Ollama content is empty")
        return content

    def _call_openai_compat(self, messages: List[Dict[str, str]], temperature: float) -> str:
        """OpenAI-compatible API call (shared by ZAI / OpenRouter)"""
        global _ZAI_LAST_CALL

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if self.backend == "zai":
            # GLM models: disable thinking via extra_body
            # (top-level is rejected by OpenAI SDK with TypeError)
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        elif self.backend == "openrouter" and "qwen" in self.model.lower():
            # Qwen3.5 official: disable thinking mode with enable_thinking=False
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}

        if self.backend == "zai":
            # ZAI 2-slot parallelization: pick slot with oldest last_call
            with _ZAI_SLOT_SELECTOR_LOCK:
                slot = min(_ZAI_SLOTS, key=lambda s: s["last_call"])
            with slot["lock"]:
                elapsed = time.time() - slot["last_call"]
                if elapsed < self.MIN_CALL_INTERVAL:
                    time.sleep(self.MIN_CALL_INTERVAL - elapsed)
                response = self.client.chat.completions.create(**kwargs)
                slot["last_call"] = time.time()
        else:
            response = self.client.chat.completions.create(**kwargs)

        content = response.choices[0].message.content
        if content is None:
            raise ValueError("LLM content is None")
        return content

    def chat(
        self,
        messages,  # List[Dict[str, str]] or str
        temperature: float = 0.7,
        max_retries: int = 6,
        num_predict: int = 8192,
    ) -> str:
        """LLM call with retry logic"""
        # If string passed, convert to user message
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        elapsed = time.time() - self._last_call_time
        if elapsed < self._interval:
            time.sleep(self._interval - elapsed)

        last_error = None
        retries = min(max_retries, 6) if self.backend == "zai" else 3  # ZAI: up to 6 retries (429 handling)

        for attempt in range(retries):
            try:
                if self.backend == "ollama":
                    content = self._call_ollama(messages, temperature, num_predict=num_predict)
                else:
                    content = self._call_openai_compat(messages, temperature)

                # Remove GLM-4.7 special token artifacts (<|user|> <|assistant|> etc.)
                content = re.sub(r"<\|[^|>]+\|>[\s\S]*", "", content).strip()
                # Remove <think>...</think> tags (with closing tag)
                content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
                # Handle unclosed <think> (preserve content before <think> if present)
                if "<think>" in content:
                    think_pos = content.find("<think>")
                    before = content[:think_pos].strip()
                    if before:
                        content = before
                    else:
                        content = re.sub(r"<think>[\s\S]*", "", content).strip()
                self._last_call_time = time.time()
                return content

            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                is_rate_limit = "429" in str(e) or "rate" in err_str or "1302" in str(e)

                if attempt < retries - 1:
                    if is_rate_limit:
                        wait = (5 * (2 ** attempt)) + random.uniform(0, 3)
                        wait = min(wait, 120)  # Cap at 120 seconds
                        # On 429: advance all slots to cool down
                        if self.backend == "zai":
                            future = time.time() + wait
                            for s in _ZAI_SLOTS:
                                s["last_call"] = max(s["last_call"], future)
                        print(f"[OracleLLM] Rate limit (attempt {attempt+1}/{retries}), waiting {wait:.0f}s...")
                    else:
                        wait = 3.0 + random.uniform(0, 2)
                        print(f"[OracleLLM] Error '{type(e).__name__}' (attempt {attempt+1}/{retries}), retrying in {wait:.1f}s...")
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"LLM call failed after {retries} attempts: {last_error}"
                    ) from last_error

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        num_predict: int = 8192,
    ) -> Dict[str, Any]:
        """Get JSON response. Extracted via regex."""
        content = self.chat(messages, temperature=temperature, num_predict=num_predict)
        # chat() already removes thinking tags, but clean up any residue
        # With closing tag
        content = re.sub(r"<think>[\s\S]*?</think>", "", content)
        # Without closing tag (when JSON appears before <think>)
        if "<think>" in content:
            think_pos = content.find("<think>")
            json_pos = content.find("{")
            if json_pos != -1 and json_pos < think_pos:
                content = content[:think_pos].strip()
            else:
                content = re.sub(r"<think>[\s\S]*", "", content).strip()

        cleaned = content.strip()

        # Remove code blocks
        cleaned = re.sub(r"```(?:json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()

        # Fix emoji quote issues (GLM-4.7 outputs various broken patterns)
        # Pattern 1: "emoji":💰,   -> "emoji":"💰",  (no quotes)
        # Pattern 2: "emoji":💰",  -> "emoji":"💰",  (missing open quote)
        # Pattern 3: "emoji":"💰", -> unchanged (normal)
        def fix_emoji_quotes(m):
            key_part = m.group(1)   # "emoji":
            val_part = m.group(2)   # emoji + optional trailing "
            # Remove trailing quote then re-wrap both sides
            val_clean = val_part.rstrip('"').strip()
            return key_part + '"' + val_clean + '"'
        cleaned = re.sub(
            r'("emoji"\s*:\s*)"?([^\s",\{\[\]][^",\{\[\]]*)"?(?=[,\}\]])',
            fix_emoji_quotes,
            cleaned,
        )

        # Extract JSON wrapped in { } using bracket stack (string-aware)
        start = cleaned.find("{")
        if start == -1:
            raise ValueError(f"No JSON found in response: {content[:200]}")

        # Track brackets with stack (accurately handles nested structures)
        bracket_stack: List[str] = []
        in_string = False
        escape_next = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue  # Don't stack brackets inside strings
            if ch == "{":
                bracket_stack.append("{")
            elif ch == "}":
                if bracket_stack and bracket_stack[-1] == "{":
                    bracket_stack.pop()
                if not bracket_stack:
                    json_str = cleaned[start:i+1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        json_str_clean = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", json_str)
                        json_str_clean = re.sub(r"\s+", " ", json_str_clean)
                        try:
                            return json.loads(json_str_clean)
                        except json.JSONDecodeError:
                            continue  # Try next {} pair
            elif ch == "[":
                bracket_stack.append("[")
            elif ch == "]":
                if bracket_stack and bracket_stack[-1] == "[":
                    bracket_stack.pop()

        # Attempt to repair incomplete JSON (truncated by token limit)
        if start != -1 and bracket_stack:
            truncated = cleaned[start:]
            # If string is mid-way through, close it
            if in_string:
                truncated += '"'
            # Generate closing brackets in reverse stack order
            closing = "".join("}" if c == "{" else "]" for c in reversed(bracket_stack))
            # Try trimming at last comma to close cleanly
            for trim in [',\n', ', ', ',']:
                last_comma = truncated.rfind(trim)
                if last_comma > 0:
                    candidate = truncated[:last_comma] + closing
                    candidate = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", candidate)
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        continue
            # If trim didn't work, just append closing brackets
            candidate = truncated + closing
            candidate = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", candidate)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        raise ValueError(f"JSON extraction failed. Response first 200 chars: {content[:200]}")
