from theos.lyra.memory.intent import MemoryIntentKind, resolve_memory_intent


def test_explicit_remember_intent() -> None:
    intent = resolve_memory_intent("LYRA, lembre que meu editor principal é o VS Code.")

    assert intent is not None
    assert intent.kind is MemoryIntentKind.REMEMBER
    assert intent.text == "meu editor principal é o VS Code"


def test_memory_search_intent() -> None:
    intent = resolve_memory_intent("LYRA, o que você lembra sobre editor?")

    assert intent is not None
    assert intent.kind is MemoryIntentKind.SEARCH
    assert intent.text == "editor"
