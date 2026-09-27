from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from theos.integrations.ai.contracts import AIProviderError, AIReply

_SYSTEM_INSTRUCTIONS = """\
Você é LYRA, a assistente central do THE OS.
Responda em português do Brasil por padrão.
Seja natural, objetiva, clara e útil.
Não afirme que executou uma ação no computador quando você não recebeu evidência de execução.
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

    def reply(self, text: str) -> AIReply:
        normalized = text.strip()
        if not normalized:
            raise ValueError("text must not be blank")

        payload = {
            "model": self._model,
            "instructions": _SYSTEM_INSTRUCTIONS,
            "input": normalized,
        }
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

        answer = _extract_output_text(body)
        if answer is None:
            raise AIProviderError("O provedor de IA não retornou texto utilizável.")

        return AIReply(
            text=answer,
            provider_id=self.provider_id,
            model=self._model,
        )


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
