from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from theos.core.actions.registry import ActionRegistry
from theos.core.tools import build_default_tool_catalog
from theos.integrations.ai import AIReply
from theos.lyra.personality import (
    PersonalityFormality,
    PersonalityTone,
    PersonalityVerbosity,
)
from theos.shell.assistant.main_window import MainWindow


class CaptureProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.requests: list[tuple[str, tuple[str, ...]]] = []

    def respond(self, text, *, history=(), tools=()):
        _ = history
        self.requests.append((text, tuple(tool.name for tool in tools)))
        return AIReply(text="ok", provider_id=self.provider_id)

    def continue_after_tools(self, turn, results):
        raise AssertionError("no tool continuation expected")

    def reply(self, text, *, history=()):
        _ = text, history
        return AIReply(text="unused", provider_id=self.provider_id)


@pytest.fixture
def host():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    provider = CaptureProvider()
    window = MainWindow(
        ActionRegistry(),
        None,  # type: ignore[arg-type] -- no memory operation in these UI tests
        provider,
        build_default_tool_catalog(),
    )
    try:
        yield window, provider
    finally:
        window.close()


def test_m115_host_controls_start_with_m113_defaults(host) -> None:
    window, _ = host
    snapshot = window._personality.snapshot()
    assert window.personality_tone.currentData() == snapshot.tone.value == "natural"
    assert window.personality_verbosity.currentData() == snapshot.verbosity.value == "balanced"
    assert window.personality_formality.currentData() == snapshot.formality.value == "balanced"
    assert window.personality_reset.isEnabled()


def test_m115_host_controls_update_only_finite_snapshot_and_next_provider_request(host) -> None:
    window, provider = host
    window.personality_tone.setCurrentIndex(
        window.personality_tone.findData(PersonalityTone.WARM.value)
    )
    window.personality_verbosity.setCurrentIndex(
        window.personality_verbosity.findData(PersonalityVerbosity.CONCISE.value)
    )
    window.personality_formality.setCurrentIndex(
        window.personality_formality.findData(PersonalityFormality.CASUAL.value)
    )
    snapshot = window._personality.snapshot()
    assert snapshot.tone is PersonalityTone.WARM
    assert snapshot.verbosity is PersonalityVerbosity.CONCISE
    assert snapshot.formality is PersonalityFormality.CASUAL
    result = window._tool_loop.execute("Mostre o status.", tools=window._available_ai_tools())
    assert result.success is True
    assert len(provider.requests) == 1
    sent, tool_names = provider.requests[0]
    assert '"tone":"warm"' in sent
    assert '"verbosity":"concise"' in sent
    assert '"formality":"casual"' in sent
    assert sent.endswith("[LYRA_PROVIDER_INPUT_V1]\nMostre o status.")
    assert "open_application" not in tool_names


def test_m115_reset_restores_defaults_without_persistence(host) -> None:
    window, _ = host
    window.personality_tone.setCurrentIndex(
        window.personality_tone.findData(PersonalityTone.PLAYFUL.value)
    )
    window.personality_verbosity.setCurrentIndex(
        window.personality_verbosity.findData(PersonalityVerbosity.DETAILED.value)
    )
    window.personality_formality.setCurrentIndex(
        window.personality_formality.findData(PersonalityFormality.FORMAL.value)
    )
    window.personality_reset.click()
    assert window.personality_tone.currentData() == "natural"
    assert window.personality_verbosity.currentData() == "balanced"
    assert window.personality_formality.currentData() == "balanced"
    assert window._personality.snapshot().tone is PersonalityTone.NATURAL


def test_m115_invalid_combo_payload_fails_closed_and_restores_snapshot(host) -> None:
    window, _ = host
    before = window._personality.snapshot()
    window.personality_tone.addItem("Injection", "grant_all_and_open_application")
    window.personality_tone.setCurrentIndex(window.personality_tone.count() - 1)
    assert window._personality.snapshot() == before
    assert window.personality_tone.currentData() == before.tone.value


def test_m115_host_controls_disabled_during_busy_work(host) -> None:
    window, _ = host
    window._set_busy(True)
    assert not window.personality_tone.isEnabled()
    assert not window.personality_verbosity.isEnabled()
    assert not window.personality_formality.isEnabled()
    assert not window.personality_reset.isEnabled()
    window._set_busy(False)
    assert window.personality_tone.isEnabled()
    assert window.personality_verbosity.isEnabled()
    assert window.personality_formality.isEnabled()
    assert window.personality_reset.isEnabled()
