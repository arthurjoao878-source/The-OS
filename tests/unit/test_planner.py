from __future__ import annotations

from theos.lyra.memory.intent import MemoryIntentKind
from theos.lyra.planning import LyraPlanner, PlanKind


def test_planner_prioritizes_memory_intent() -> None:
    plan = LyraPlanner().plan("LYRA, lembre que meu editor é o VS Code.")

    assert plan.kind is PlanKind.MEMORY
    assert plan.memory_intent is not None
    assert plan.memory_intent.kind is MemoryIntentKind.REMEMBER
    assert plan.action_request is None


def test_planner_routes_registered_local_action_candidate() -> None:
    plan = LyraPlanner().plan("LYRA, abre o Discord")

    assert plan.kind is PlanKind.ACTION
    assert plan.action_request is not None
    assert plan.action_request.action == "open_application"
    assert plan.memory_intent is None


def test_planner_routes_unmatched_text_to_conversation() -> None:
    plan = LyraPlanner().plan("Qual foi a última coisa que eu disse?")

    assert plan.kind is PlanKind.CONVERSATION
    assert plan.memory_intent is None
    assert plan.action_request is None
