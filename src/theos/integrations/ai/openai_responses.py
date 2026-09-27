from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx

from theos.core.tools import ToolCall, ToolDefinition
from theos.integrations.ai.contracts import AIProviderError, AIReply, AIResponse
from theos.lyra.context import ConversationTurn

_SYSTEM_INSTRUCTIONS = """\
Você é LYRA, a assistente central do THE OS.
Responda em português do Brasil por padrão.
Seja natural, objetiva, clara e útil.
Quando ferramentas estiverem disponíveis, use uma ferramenta apenas se o pedido realmente
exigir uma ação local no computador.
Nunca afirme que uma ação foi executada antes de receber a evidência do THE OS.
Não invente memórias. Memória persistente é fornecida separadamente pelo THE OS.
"""


class OpenAIResponsesProvider:
    provider_id = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        normalized_key = api_key.strip()
        normalized_model = model.strip()
        normalized_base_url = base_url.rstrip("/").strip()
        if not normalized_key:
            raise ValueError("api_key must not be blank")
        if not normalized_model:
            raise ValueError("model must not be blank")
        if not normalized_base_url:
            raise ValueError("base_url must not be blank")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._api_key = normalized_key
        self._model = normalized_model
        self._base_url = normalized_base_url
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def model(self) -> str:
        return self._model

    def respond(
        self,
        text: str,
        *,
        history: tuple[ConversationTurn, ...] = (),
        tools: tuple[ToolDefinition, ...] = (),
    ) -> AIResponse:
        normalized = text.strip()
        if not normalized:
            raise ValueError("text must not be blank")

        input_value: str | list[dict[str, str]]
        if history:
            input_value = [
                {
                    "role": turn.role.value,
                    "content": turn.text,
                }
                for turn in history
            ]
            input_value.append({"role": "user", "content": normalized})
        else:
            input_value = normalized

        payload: dict[str, object] = {
            "model": self._model,
            "instructions": _SYSTEM_INSTRUCTIONS,
            "input": input_value,
            "store": False,
        }
        if tools:
            payload["tools"] = [_encode_tool(definition) for definition in tools]
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            if self._client is None:
                with httpx.Client(timeout=self._timeout_seconds) as client:
                    response = client.post(
                        f"{self._base_url}/responses",
                        headers=headers,
                        json=payload,
                    )
            else:
                response = self._client.post(
                    f"{self._base_url}/responses",
                    headers=headers,
                    json=payload,
                )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exception:
            raise AIProviderError(
                f"Falha no provedor de IA (HTTP {exception.response.status_code})."
            ) from exception
        except httpx.HTTPError as exception:
            raise AIProviderError("Não consegui conectar ao provedor de IA.") from exception
        except ValueError as exception:
            raise AIProviderError("O provedor de IA retornou uma resposta inválida.") from exception

        tool_call = _extract_tool_call(body)
        if tool_call is not None:
            return tool_call

        answer = _extract_output_text(body)
        if answer is None:
            raise AIProviderError("O provedor de IA não retornou texto nem ferramenta utilizável.")

        return AIReply(
            text=answer,
            provider_id=self.provider_id,
            model=self._model,
        )

    def reply(
        self,
        text: str,
        *,
        history: tuple[ConversationTurn, ...] = (),
    ) -> AIReply:
        response = self.respond(text, history=history)
        if not isinstance(response, AIReply):
            raise AIProviderError("O provedor retornou uma ferramenta em modo de conversa.")
        return response


def _encode_tool(definition: ToolDefinition) -> dict[str, object]:
    return {
        "type": "function",
        "name": definition.name,
        "description": definition.description,
        "parameters": definition.parameters,
        "strict": True,
    }


def _extract_tool_call(body: object) -> ToolCall | None:
    if not isinstance(body, Mapping):
        return None

    output = body.get("output")
    if not isinstance(output, list):
        return None

    calls: list[ToolCall] = []
    for item in output:
        if not isinstance(item, Mapping) or item.get("type") != "function_call":
            continue

        name = item.get("name")
        raw_arguments = item.get("arguments")
        if not isinstance(name, str) or not name.strip() or not isinstance(raw_arguments, str):
            raise AIProviderError("O provedor retornou uma chamada de ferramenta inválida.")

        try:
            decoded = json.loads(raw_arguments)
        except json.JSONDecodeError as exception:
            raise AIProviderError(
                "O provedor retornou argumentos de ferramenta inválidos."
            ) from exception

        if not isinstance(decoded, dict) or not all(isinstance(key, str) for key in decoded):
            raise AIProviderError("Os argumentos da ferramenta precisam ser um objeto JSON.")

        calls.append(ToolCall(name=name, arguments=decoded))

    if len(calls) > 1:
        raise AIProviderError(
            "A LYRA recebeu mais de uma ação simultânea; esta versão executa uma por vez."
        )

    return calls[0] if calls else None


def _extract_output_text(body: object) -> str | None:
    if not isinstance(body, Mapping):
        return None

    direct = body.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    output = body.get("output")
    if not isinstance(output, list):
        return None

    parts: list[str] = []
    for item in output:
        if not isinstance(item, Mapping):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, Mapping):
                continue
            part_type = part.get("type")
            value: Any = part.get("text")
            if part_type == "output_text" and isinstance(value, str) and value.strip():
                parts.append(value.strip())

    if not parts:
        return None
    return "\n".join(parts)
