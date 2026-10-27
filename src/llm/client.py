"""Client LLM (Groq — OpenAI-compatible API) with forced structured output."""
from __future__ import annotations

import json
import logging
from typing import Any

from config import settings
from .prompts import ANSWER_TOOL, DERJA_REFORMULATION_PROMPT

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


def _to_openai_tool(anthropic_style_tool: dict) -> dict:
   """Converts an Anthropic-style tool schema {name, description, input_schema} 
   into the OpenAI/Groq format {type: function, function: {...}}."""
    return {
        "type": "function",
        "function": {
            "name": anthropic_style_tool["name"],
            "description": anthropic_style_tool["description"],
            "parameters": anthropic_style_tool["input_schema"],
        },
    }


class LLMClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        key = api_key or settings.groq_api_key
        if not key:
            raise LLMError(
                "Missing GROQ_API_KEY. Add it to the .env file."
            )
        from openai import OpenAI
        self._client = OpenAI(api_key=key, base_url=settings.groq_base_url)
        self.model = model or settings.llm_model

    # ------------------------------------------------------------------ #
    def answer(self, system: str, context: str, question: str,
               history: list[dict] | None = None) -> dict[str, Any]:
        """Generate the structured legal response."""
        user_content = (
            f"CONTEXTE (articles de loi tunisiens) :\n\n{context}\n\n"
            f"---\n\nQUESTION DE L'UTILISATEUR :\n{question}"
        )

        messages: list[dict] = [{"role": "system", "content": system}]
        for turn in (history or [])[-6:]:        # fenêtre glissante
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": user_content})

        tool = _to_openai_tool(ANSWER_TOOL)

        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                max_tokens=settings.llm_max_tokens,
                temperature=settings.llm_temperature,
                messages=messages,
                tools=[tool],
                tool_choice={"type": "function",
                            "function": {"name": "emit_legal_answer"}},
            )
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"Appel LLM échoué : {exc}") from exc

        message = resp.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []
        for call in tool_calls:
            if call.function.name == "emit_legal_answer":
                try:
                    data = json.loads(call.function.arguments)
                except (json.JSONDecodeError, TypeError) as exc:
                    raise LLMError(
                        f"Réponse JSON invalide du modèle : {exc}"
                    ) from exc
                data.setdefault("citations", [])
                data.setdefault("confidence_note", "")
                return data

        raise LLMError("The model didn't return a structured response.")

    # ------------------------------------------------------------------ #
    def reformulate_derja(self, question: str) -> str:
        """Pre-processing step: Derja -> Standard Arabic."""
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                max_tokens=200,
                temperature=0.0,
                messages=[{
                    "role": "user",
                    "content": DERJA_REFORMULATION_PROMPT.format(question=question),
                }],
            )
            text = (resp.choices[0].message.content or "").strip()
            return text.splitlines()[0].strip() if text else question
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed Derja rephrasing: %s", exc)
            return question
