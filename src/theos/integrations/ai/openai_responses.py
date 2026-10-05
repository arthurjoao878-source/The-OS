from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import httpx

from theos.core.tools import ToolCall, ToolDefinition
from theos.integrations.ai.contracts import (
    AIContinuation,
    AIProviderError,
    AIReply,
    AIResponse,
    AIToolResult,
    AIToolTurn,
)
from theos.lyra.context import ConversationTurn

_SYSTEM_INSTRUCTIONS = """\
Você é LYRA, a assistente central do THE OS.
Responda em português do Brasil por padrão.
Seja natural, objetiva, clara e útil.
Quando ferramentas estiverem disponíveis, use uma ferramenta apenas se o pedido realmente
exigir uma ação local no computador.
Se o usuário pedir várias ações locais, conclua todas as ações solicitadas antes da resposta
final. Se você chamar uma ferramenta por vez, depois de receber o resultado continue com a
próxima ação pendente. Não encerre o pedido após apenas a primeira etapa.
Nunca afirme que uma ação foi executada antes de receber a evidência do THE OS.
Em workflows de arquivo texto existente, quando o conteúdo atual for necessário para editar
com segurança, leia o trecho relevante com read_text_file ou read_text_lines antes da
mutação. Prefira replace_text_literal ou replace_text_block a reescrever o arquivo inteiro
quando a mudança for estreita. Após uma mutação, baseie a conclusão na evidência retornada
pelo THE OS, incluindo write_verified e SHA-256 quando disponíveis; isso não prova que o
objetivo maior do usuário foi alcançado.
Não invente memórias. Memória persistente é fornecida separadamente pelo THE OS.
"""


@dataclass(frozen=True, slots=True)
class _OpenAIContinuationState:
    replay_input: tuple[dict[str, object], ...]
    tools: tuple[ToolDefinition, ...]


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

        replay_input = [
            {
                "role": turn.role.value,
                "content": turn.text,
            }
            for turn in history
        ]
        replay_input.append({"role": "user", "content": normalized})

        body = self._create_response(
            input_value=normalized if not history else replay_input,
            tools=tools,
        )
        return self._decode_response(
            body,
            replay_input=tuple(replay_input),
            tools=tools,
        )

    def continue_after_tools(
        self,
        turn: AIToolTurn,
        results: tuple[AIToolResult, ...],
    ) -> AIResponse:
        if turn.provider_id != self.provider_id:
            raise AIProviderError("A continuação pertence a outro provedor de IA.")
        if turn.continuation.provider_id != self.provider_id:
            raise AIProviderError("O estado de continuação pertence a outro provedor de IA.")

        state = turn.continuation.state
        if not isinstance(state, _OpenAIContinuationState):
            raise AIProviderError("O estado de continuação da IA é inválido.")

        expected_call_ids = tuple(call.call_id for call in turn.calls)
        if any(call_id is None for call_id in expected_call_ids):
            raise AIProviderError("A chamada de ferramenta não possui call_id.")

        actual_call_ids = tuple(result.call_id for result in results)
        if expected_call_ids != actual_call_ids:
            raise AIProviderError("Os resultados não correspondem às chamadas de ferramenta.")

        replay_input = [deepcopy(item) for item in state.replay_input]
        replay_input.extend(
            {
                "type": "function_call_output",
                "call_id": result.call_id,
                "output": result.output,
            }
            for result in results
        )

        body = self._create_response(
            input_value=replay_input,
            tools=state.tools,
        )
        return self._decode_response(
            body,
            replay_input=tuple(replay_input),
            tools=state.tools,
        )

    def reply(
        self,
        text: str,
        *,
        history: tuple[ConversationTurn, ...] = (),
    ) -> AIReply:
        response = self.respond(text, history=history)
        if not isinstance(response, AIReply):
            raise AIProviderError("O provedor retornou ferramenta em modo de conversa.")
        return response

    def _create_response(
        self,
        *,
        input_value: object,
        tools: tuple[ToolDefinition, ...],
    ) -> Mapping[str, object]:
        payload: dict[str, object] = {
            "model": self._model,
            "instructions": _SYSTEM_INSTRUCTIONS,
            "input": input_value,
            "store": False,
        }
        if tools:
            payload["tools"] = [_encode_tool(definition) for definition in tools]
            payload["tool_choice"] = "auto"
            payload["parallel_tool_calls"] = False
            payload["include"] = ["reasoning.encrypted_content"]

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

        if not isinstance(body, Mapping):
            raise AIProviderError("O provedor de IA retornou um objeto inválido.")
        return body

    def _decode_response(
        self,
        body: Mapping[str, object],
        *,
        replay_input: tuple[dict[str, object], ...],
        tools: tuple[ToolDefinition, ...],
    ) -> AIResponse:
        output = body.get("output")
        output_items = _copy_output_items(output)
        calls = _extract_tool_calls(output_items)

        if calls:
            if len(calls) > 1:
                raise AIProviderError(
                    "O provedor retornou múltiplas ferramentas mesmo com execução serial."
                )
            continuation_input = (
                *deepcopy(list(replay_input)),
                *deepcopy(output_items),
            )
            return AIToolTurn(
                calls=tuple(calls),
                continuation=AIContinuation(
                    provider_id=self.provider_id,
                    state=_OpenAIContinuationState(
                        replay_input=continuation_input,
                        tools=tools,
                    ),
                ),
                provider_id=self.provider_id,
                model=self._model,
            )

        answer = _extract_output_text(body)
        if answer is None:
            raise AIProviderError("O provedor de IA não retornou texto nem ferramenta utilizável.")

        return AIReply(
            text=answer,
            provider_id=self.provider_id,
            model=self._model,
        )


def _encode_tool(definition: ToolDefinition) -> dict[str, object]:
    return {
        "type": "function",
        "name": definition.name,
        "description": definition.description,
        "parameters": definition.parameters,
        "strict": True,
    }


def _copy_output_items(output: object) -> list[dict[str, object]]:
    if output is None:
        return []
    if not isinstance(output, list):
        raise AIProviderError("A saída estruturada do provedor é inválida.")

    copied: list[dict[str, object]] = []
    for item in output:
        if not isinstance(item, Mapping):
            raise AIProviderError("Um item de saída do provedor é inválido.")
        copied.append(deepcopy(dict(item)))
    return copied


def _extract_tool_calls(output: list[dict[str, object]]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for item in output:
        if item.get("type") != "function_call":
            continue

        name = item.get("name")
        raw_arguments = item.get("arguments")
        call_id = item.get("call_id")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(raw_arguments, str)
            or not isinstance(call_id, str)
            or not call_id.strip()
        ):
            raise AIProviderError("O provedor retornou uma chamada de ferramenta inválida.")

        try:
            decoded = json.loads(raw_arguments)
        except json.JSONDecodeError as exception:
            raise AIProviderError(
                "O provedor retornou argumentos de ferramenta inválidos."
            ) from exception

        if not isinstance(decoded, dict) or not all(isinstance(key, str) for key in decoded):
            raise AIProviderError("Os argumentos da ferramenta precisam ser um objeto JSON.")

        calls.append(
            ToolCall(
                name=name,
                arguments=decoded,
                call_id=call_id,
            )
        )
    return calls


def _extract_output_text(body: Mapping[str, object]) -> str | None:
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
