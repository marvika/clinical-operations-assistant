"""Chat-model factory.

The Azure OpenAI resource is reached through its OpenAI-v1-compatible
endpoint, so the standard ``ChatOpenAI`` client works with just a base_url.

Of the two provided deployments, only ``gpt-4.1-mini`` reliably supports tool
calling; ``gpt-5.2-chat`` is a chat-tuned variant documented to drop tools
(see docs/decisions.md), so it is not used.
"""

from langchain_openai import ChatOpenAI

from app.config import settings


def make_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.model_name,
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        temperature=0,  # determinism aids the frozen-clock case and the evals
    )
