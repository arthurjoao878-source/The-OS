from __future__ import annotations

import json

import httpx

from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import (
    AIReply,
    AIToolResult,
    AIToolTurn,
    OpenAIResponsesProvider,
    UnavailableAIProvider,
)
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
    assert captured["body"]["input"] == "Quem é você?"
    assert captured["body"]["store"] is False
    assert "tools" not in captured["body"]
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


def test_openai_provider_returns_serial_tool_turn() -> None:
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

    response = provider.respond(
        "Você consegue iniciar o Bloco de Notas para mim?",
        tools=build_default_tool_catalog().definitions(),
    )

    assert isinstance(response, AIToolTurn)
    assert response.calls[0].name == "open_application"
    assert response.calls[0].arguments == {"application": "Bloco de Notas"}
    assert response.calls[0].call_id == "call_test"

    body = captured["body"]
    assert body["tool_choice"] == "auto"
    assert body["parallel_tool_calls"] is False
    assert body["store"] is False
    assert body["include"] == ["reasoning.encrypted_content"]
    client.close()


def test_openai_provider_replays_tool_result_and_can_request_next_action() -> None:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        requests.append(body)

        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "output": [
                        {
                            "type": "function_call",
                            "name": "open_application",
                            "arguments": '{"application":"Bloco de Notas"}',
                            "call_id": "call_1",
                        }
                    ]
                },
            )

        if len(requests) == 2:
            return httpx.Response(
                200,
                json={
                    "output": [
                        {
                            "type": "function_call",
                            "name": "open_application",
                            "arguments": '{"application":"Google Chrome"}',
                            "call_id": "call_2",
                        }
                    ]
                },
            )

        return httpx.Response(
            200,
            json={"output_text": "Bloco de Notas e Google Chrome foram abertos."},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAIResponsesProvider(
        api_key="test-key",
        model="test-model",
        client=client,
    )
    tools = build_default_tool_catalog().definitions()

    first = provider.respond(
        "Inicie o Bloco de Notas e depois o Google Chrome.",
        tools=tools,
    )
    assert isinstance(first, AIToolTurn)

    second = provider.continue_after_tools(
        first,
        (
            AIToolResult(
                call_id="call_1",
                output='{"success":true,"message":"Notepad aberto."}',
            ),
        ),
    )
    assert isinstance(second, AIToolTurn)
    assert second.calls[0].arguments == {"application": "Google Chrome"}

    final = provider.continue_after_tools(
        second,
        (
            AIToolResult(
                call_id="call_2",
                output='{"success":true,"message":"Google Chrome aberto."}',
            ),
        ),
    )
    assert isinstance(final, AIReply)
    assert final.text == "Bloco de Notas e Google Chrome foram abertos."

    second_input = requests[1]["input"]
    assert second_input[-1] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": '{"success":true,"message":"Notepad aberto."}',
    }
    assert requests[1]["parallel_tool_calls"] is False
    assert requests[2]["parallel_tool_calls"] is False
    client.close()
