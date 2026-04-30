"""
Models using bare SDK rather than langchain / dify. Such SDKs often make tool using or JSON schema difficult.
"""

import functools
from enum import StrEnum
from typing import TypeVar

import anthropic
import anthropic.resources
from pydantic import BaseModel

import ihate_work.o11y as o11y

logger, *_ = o11y.get_o11y(__name__)

ModelClass = TypeVar("ModelClass", bound=BaseModel)


class ClaudeBareModel(StrEnum):
    # claude models hosted on GCP
    # list: https://console.cloud.google.com/vertex-ai/model-garden
    gcp_haiku35 = "claude-3-5-haiku@20241022"
    gcp_haiku35_20241022 = "claude-3-5-haiku@20241022"
    gcp_sonnet_v2 = "claude-3-5-sonnet-v2@20241022"
    gcp_sonnet_v2_20241022 = "claude-3-5-sonnet-v2@20241022"

    def shared_client(self) -> anthropic.AnthropicVertex:
        return _shared_client()

    def complete_with_json(
        self,
        user_messages: list[str],
        tool_model: type[ModelClass],
        *,
        system_message: str | None = None,
        **kwargs,
    ) -> ModelClass:
        def create_response() -> anthropic.types.Message:
            client = self.shared_client()
            return client.messages.create(
                model=self.value,
                max_tokens=kwargs.get("max_tokens", 2000),
                tools=[
                    {
                        "name": "report-result",
                        "description": "report the result of the task",
                        "input_schema": tool_model.model_json_schema(),
                    }
                ],
                tool_choice={"type": "tool", "name": "report-result"},
                **({"system": system_message} if system_message else {}),
                messages=[{"role": "user", "content": m} for m in user_messages],
                **(_pick_args(kwargs, ["temperature", "top_k", "top_p"])),
            )

        response = create_response()

        assert len(response.content) == 1, "unexpected response length"
        for msg in response.content:
            if msg.type == "tool_use":
                return tool_model.model_validate(msg.input)
        logger.debug("unexpected msg", msg_type=msg.type, msg=str(msg))
        assert False, "unexpected response content"


@functools.lru_cache(maxsize=1)
def _shared_client() -> anthropic.AnthropicVertex:
    # shared across all instances
    return anthropic.AnthropicVertex(
        project_id="thecoo-data-platform",
        region="us-east5",
    )


def _pick_args(kwargs: dict, keys: list[str]) -> dict:
    return {k: kwargs[k] for k in keys if k in kwargs}
