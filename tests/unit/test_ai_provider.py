from __future__ import annotations

import json

import httpx

from theos.integrations.ai import OpenAIResponsesProvider, UnavailableAIProvider
from theos.integrations.ai.provider_factory import build_ai_provider


def test_ai_provider_is_disabled_without_configuration() -> None:
    provider = build_ai_provider({}, load_environment_file=False)

    reply = provider.reply("Olá")

    assert isinstance(provider, UnavailableAIProvider)
    assert "não está configurada" in reply.text


def test_openai_responses_provider_extracts_text_without_real_network() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Olá. Eu sou a LYRA.",
                            }
                        ],
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAIResponsesProvider(
        api_key="test-key",
        model="test-model",
        client=client,
    )

    reply = provider.reply("Quem é você?")

    assert reply.text == "Olá. Eu sou a LYRA."
    assert reply.provider_id == "openai"
    assert reply.model == "test-model"
    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["authorization"] == "Bearer test-key"
    assert captured["body"] == {
        "model": "test-model",
        "instructions": (
            "Você é LYRA, a assistente central do THE OS.\n"
            "Responda em português do Brasil por padrão.\n"
            "Seja natural, objetiva, clara e útil.\n"
            "Não afirme que executou uma ação no computador quando você não recebeu "
            "evidência de execução.\n"
            "Não invente memórias. Memória persistente é fornecida separadamente pelo THE OS.\n"
        ),
        "input": "Quem é você?",
    }
    client.close()
