from theos.lyra.conversation.smoke_intent import resolve_smoke_intent


def test_intent_open_application() -> None:
    request = resolve_smoke_intent("LYRA, abre o Discord.")
    assert request is not None
    assert request.action == "open_application"
    assert request.arguments["application"] == "Discord"