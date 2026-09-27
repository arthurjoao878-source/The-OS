from __future__ import annotations

import json

import httpx

from theos.core.tools import ToolCall, build_default_tool_catalog
from theos.integrations.ai import OpenAIResponsesProvider, UnavailableAIProvider
from theos.integrations.ai.provider_factory import build_ai_provider
from theos.lyra.context import ConversationRole, ConversationTurn


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
            "Quando ferramentas estiverem disponíveis, use uma ferramenta apenas se o pedido "
            "realmente\nexigir uma ação local no computador.\n"
            "Nunca afirme que uma ação foi executada antes de receber a evidência do THE OS.\n"
            "Não invente memórias. Memória persistente é fornecida separadamente pelo THE OS.\n"
        ),
        "input": "Quem é você?",
        "store": False,
    }
    client.close()


def test_openai_responses_provider_sends_bounded_session_history() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"output_text": "Aurora."})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAIResponsesProvider(
        api_key="test-key",
        model="test-model",
        client=client,
    )
    history = (
        ConversationTurn(
            role=ConversationRole.USER,
            text="O codinome temporário é Aurora.",
        ),
        ConversationTurn(
            role=ConversationRole.ASSISTANT,
            text="Entendido.",
        ),
    )

    reply = provider.reply("Qual é o codinome?", history=history)

    assert reply.text == "Aurora."
    assert captured["body"]["input"] == [
        {"role": "user", "content": "O codinome temporário é Aurora."},
        {"role": "assistant", "content": "Entendido."},
        {"role": "user", "content": "Qual é o codinome?"},
    ]
    assert captured["body"]["store"] is False
    client.close()


def test_openai_provider_returns_allowlisted_function_call() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "function_call",
                        "name": "open_application",
                        "arguments": '{"application":"Bloco de Notas"}',
                        "call_id": "call_test",
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
    tools = build_default_tool_catalog().definitions()

    response = provider.respond(
        "Você consegue iniciar o Bloco de Notas para mim?",
        tools=tools,
    )

    assert isinstance(response, ToolCall)
    assert response.name == "open_application"
    assert response.arguments == {"application": "Bloco de Notas"}

    body = captured["body"]
    assert body["tool_choice"] == "auto"
    assert body["store"] is False
    assert body["tools"] == [
        {
            "type": "function",
            "name": "open_application",
            "description": (
                "Abre um aplicativo instalado no computador Windows do usuário. "
                "Use quando o usuário pedir para abrir, iniciar ou executar um aplicativo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "application": {
                        "type": "string",
                        "description": "Nome do aplicativo que o usuário quer abrir.",
                    }
                },
                "required": ["application"],
                "additionalProperties": False,
            },
            "strict": True,
        }
    ]
    client.close()
