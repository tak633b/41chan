"""
Oracle LLM クライアント
ZAI / Ollama / OpenRouter 切替対応。
環境変数 ORACLE_LLM_BACKEND で切替（zai / ollama / openrouter）。
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

# ZAI用タイムスロット並列化（2スロット交互発射で実効1.5秒間隔）
_ZAI_SLOTS = [
    {"lock": threading.Lock(), "last_call": 0.0},
    {"lock": threading.Lock(), "last_call": 0.0},
]
_ZAI_SLOT_SELECTOR_LOCK = threading.Lock()  # スロット選択のアトミック性保証


class OracleLLMClient:
    """LLMクライアント（ZAI / Ollama / OpenRouter 切替対応、リトライ付き）"""

    # ZAI設定
    ZAI_API_KEY = os.environ.get("ORACLE_ZAI_API_KEY", "")
    ZAI_BASE_URL = "https://api.z.ai/api/coding/paas/v4"
    ZAI_MODEL = os.environ.get("ORACLE_ZAI_MODEL", "glm-5")

    # Ollama設定
    OLLAMA_API_URL = "http://localhost:11434/api/chat"
    OLLAMA_MODEL = os.environ.get("ORACLE_OLLAMA_MODEL", "qwen3.5:9b")

    # OpenRouter設定
    OPENROUTER_API_KEY = os.environ.get(
        "OPENROUTER_API_KEY",
        "***REDACTED_OPENROUTER***",
    )
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL = os.environ.get(
        "OPENROUTER_MODEL",
        "nvidia/nemotron-3-super-120b-a12b:free",
    )

    MIN_CALL_INTERVAL = 3.0  # ZAI用
    OLLAMA_CALL_INTERVAL = 0.1  # ローカルモデルなので最小限
    OPENROUTER_CALL_INTERVAL = 1.0  # 無料枠は控えめに

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
            self.client = None  # Ollama は requests 直接
            self.model = model or os.environ.get("ORACLE_OLLAMA_MODEL", self.OLLAMA_MODEL)
            self._interval = self.OLLAMA_CALL_INTERVAL

        self._last_call_time = 0.0
        print(f"[OracleLLM] バックエンド: {self.backend} | モデル: {self.model}")

    def _call_ollama(self, messages: List[Dict[str, str]], temperature: float, num_predict: int = 8192) -> str:
        """Ollama native API 直接呼び出し"""
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
        """OpenAI互換API呼び出し（ZAI / OpenRouter共通）"""
        global _ZAI_LAST_CALL

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if self.backend == "zai":
            # GLM-5はデフォルトでthinking ON → 明示的に無効化（速度・トークン節約）
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        elif self.backend == "openrouter" and "qwen" in self.model.lower():
            # Qwen3.5公式: enable_thinking=False で思考モード無効化
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}

        if self.backend == "zai":
            # ZAI 2スロット並列: last_callが古いスロットを選んで交互発射
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
        messages,  # List[Dict[str, str]] または str
        temperature: float = 0.7,
        max_retries: int = 6,
        num_predict: int = 8192,
    ) -> str:
        """リトライ付きLLM呼び出し"""
        # 文字列が渡された場合はuserメッセージに変換
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        elapsed = time.time() - self._last_call_time
        if elapsed < self._interval:
            time.sleep(self._interval - elapsed)

        last_error = None
        retries = min(max_retries, 6) if self.backend == "zai" else 3  # ZAIは最大6回（429対策）

        for attempt in range(retries):
            try:
                if self.backend == "ollama":
                    content = self._call_ollama(messages, temperature, num_predict=num_predict)
                else:
                    content = self._call_openai_compat(messages, temperature)

                # <think>...</think> タグ除去（閉じタグあり）
                content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
                # 閉じタグなしの場合（<think>の前にコンテンツがあれば保持）
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
                        wait = min(wait, 120)  # 最大120秒に制限
                        # 429時は全スロットをwait秒先に進めて冷却
                        if self.backend == "zai":
                            future = time.time() + wait
                            for s in _ZAI_SLOTS:
                                s["last_call"] = max(s["last_call"], future)
                        print(f"[OracleLLM] レート制限 (試行{attempt+1}/{retries})、{wait:.0f}秒待機...")
                    else:
                        wait = 3.0 + random.uniform(0, 2)
                        print(f"[OracleLLM] エラー '{type(e).__name__}' (試行{attempt+1}/{retries})、{wait:.1f}秒後リトライ...")
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"LLM呼び出しが{retries}回失敗しました: {last_error}"
                    ) from last_error

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        num_predict: int = 8192,
    ) -> Dict[str, Any]:
        """JSON応答を取得。regex抽出。"""
        content = self.chat(messages, temperature=temperature, num_predict=num_predict)
        # chat()で既にthinking除去済みだが、念のため残りを除去
        # 閉じタグありの場合
        content = re.sub(r"<think>[\s\S]*?</think>", "", content)
        # 閉じタグなしの場合（<think>以降にJSONがないパターン）
        if "<think>" in content:
            # <think>の前にJSONがあればそれを保持
            think_pos = content.find("<think>")
            json_pos = content.find("{")
            if json_pos != -1 and json_pos < think_pos:
                content = content[:think_pos].strip()
            else:
                content = re.sub(r"<think>[\s\S]*", "", content).strip()
        
        cleaned = content.strip()
        
        # コードブロック除去
        cleaned = re.sub(r"```(?:json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()

        # クォートなし絵文字を修正: "emoji":🧠, → "emoji":"🧠",
        cleaned = re.sub(r'("emoji"\s*:\s*)([^\s",\{\[\]]+)', lambda m: m.group(1) + '"' + m.group(2) + '"', cleaned)

        # { } で囲まれたJSONを抽出（文字列対応の深さカウンタ）
        # まず最外側の {} ペアを段階的に探す
        start = cleaned.find("{")
        if start == -1:
            raise ValueError(f"レスポンス中にJSONが見つかりませんでした: {content[:200]}")

        # スタックで開き括弧を追跡（閉じる順序を正確に復元するため）
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
                continue  # 文字列内の括弧はスタックに積まない
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
                            continue  # 次の {} ペアを試す
            elif ch == "[":
                bracket_stack.append("[")
            elif ch == "]":
                if bracket_stack and bracket_stack[-1] == "[":
                    bracket_stack.pop()

        # 不完全なJSON修復（トークン上限で切れた場合）
        if start != -1 and bracket_stack:
            truncated = cleaned[start:]
            # 文字列途中で切れている場合は閉じクォートを補完
            if in_string:
                truncated += '"'
            # スタックの逆順で閉じ括弧を生成（正しい閉じ順）
            closing = "".join("}" if c == "{" else "]" for c in reversed(bracket_stack))
            # まず末尾の不完全な値をカンマで切り捨てて閉じる
            for trim in [',\n', ', ', ',']:
                last_comma = truncated.rfind(trim)
                if last_comma > 0:
                    candidate = truncated[:last_comma] + closing
                    candidate = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", candidate)
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        continue
            # カンマ切り捨てでダメなら、そのまま閉じ括弧を追加
            candidate = truncated + closing
            candidate = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", candidate)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        raise ValueError(f"JSON抽出失敗。元テキスト先頭200字: {content[:200]}")
