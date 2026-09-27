from __future__ import annotations

import os
from collections.abc import Mapping

from dotenv import load_dotenv

from theos.integrations.ai.contracts import AIProvider, UnavailableAIProvider
from theos.integrations.ai.openai_responses import OpenAIResponsesProvider


def build_ai_provider(
    environment: Mapping[str, str] | None = None,
    *,
    load_environment_file: bool = True,
) -> AIProvider:
    if load_environment_file:
        load_dotenv()

    env = os.environ if environment is None else environment
    provider = env.get("THEOS_AI_PROVIDER", "").strip().lower()

    if not provider:
        return UnavailableAIProvider(
            "Conversa por IA ainda não está configurada. "
            "Configure THEOS_AI_PROVIDER, THEOS_AI_MODEL e THEOS_AI_API_KEY no .env."
        )

    if provider != "openai":
        return UnavailableAIProvider(
            f"O provedor de IA {provider!r} ainda não possui adaptador no THE OS."
        )

    model = env.get("THEOS_AI_MODEL", "").strip()
    api_key = env.get("THEOS_AI_API_KEY", "").strip()
    base_url = env.get("THEOS_AI_BASE_URL", "https://api.openai.com/v1").strip()

    if not model or not api_key:
        return UnavailableAIProvider(
            "O provedor OpenAI foi selecionado, mas THEOS_AI_MODEL e "
            "THEOS_AI_API_KEY precisam estar configurados."
        )

    return OpenAIResponsesProvider(
        api_key=api_key,
        model=model,
        base_url=base_url,
    )
