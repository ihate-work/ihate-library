import logging
from enum import StrEnum

from .chat_comp_model import ChatCompModel
from .langfuse import setup_langfuse_otel


class ChatCompModels(StrEnum):
    # Google Gemini (the one uses $GEMINI_API_KEY)
    # model list: https://ai.google.dev/gemini-api/docs/models
    gemini25_pro_exp = "gemini/gemini-2.5-pro-exp-03-25"
    gemini20_flash = "gemini/gemini-2.0-flash"
    gemini20_flash_lite = "gemini/gemini-2.0-flash-lite"
    gemini15_flash = "gemini/gemini-1.5-flash"
    gemini15_flash_8b = "gemini/gemini-1.5-flash-8b"

    # Googel Vertex AI (the one uses SA json key)
    # list: https://console.cloud.google.com/vertex-ai/model-garden
    # TODO

    # Claude via Anthropic
    # list: https://docs.anthropic.com/en/docs/about-claude/models/all-models
    claude_40_sonnet = "anthropic/claude-sonnet-4-20250514"
    claude_37_sonnet = "anthropic/claude-3-7-sonnet-latest"
    claude_37_sonnet_20250219 = "anthropic/claude-3-7-sonnet@20250219"
    claude_35_haiku = "anthropic/claude-3-5-haiku-latest"
    claude_35_sonnet = "anthropic/claude-3-5-sonnet-20241022"

    # Claude via Vertex AI
    # list: https://console.cloud.google.com/vertex-ai/model-garden
    vertex_claude_haiku35 = "claude-3-5-haiku@20241022"
    vertex_claude_haiku35_20241022 = "claude-3-5-haiku@20241022"
    vertex_claude_sonnet35_v2 = "claude-3-5-sonnet-v2@20241022"
    vertex_claude_sonnet35_v2_20241022 = "claude-3-5-sonnet-v2@20241022"
    vertex_claude_sonnet37 = "claude-3-7-sonnet@20250219"
    vertex_claude_sonnet37_20250219 = "claude-3-7-sonnet@20250219"

    # ollama
    # list: https://ollama.com/models
    ollama_deepseek_r1_14b = "ollama/deepseek-r1:14b"
    # ollama_deepseek_r1_14b = "ollama/deepseek-r1:14b"

    def to_model(self) -> ChatCompModel:
        return ChatCompModel(model=self.value)


def setup_litellm_logging(lvl=logging.WARNING):
    from litellm._logging import (
        verbose_logger,
        verbose_proxy_logger,
        verbose_router_logger,
    )

    for logger in [verbose_logger, verbose_proxy_logger, verbose_router_logger]:
        logger.setLevel(lvl)


__all__ = [
    "ChatCompModels",
    "ChatCompModel",
    "setup_litellm_logging",
    "setup_langfuse_otel",
]
