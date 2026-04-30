"""
Models using bare SDK rather than langchain / dify. Such SDKs often make tool using or JSON schema difficult.
"""

import functools
import os
from enum import StrEnum
from typing import TypeVar

import anthropic
from pydantic import BaseModel

import ihate_work.o11y as o11y

logger, *_ = o11y.get_o11y(__name__)

ModelClass = TypeVar("ModelClass", bound=BaseModel)


class ClaudeBareModel(StrEnum):
    # claude models hosted on GCP
    # list: https://console.cloud.google.com/vertex-ai/model-garden
    gcp_haiku35 = "claude-3-5-haiku@20241022"
    gcp_haiku35_20241022 = "claude-3-5-haiku@20241022"
    gcp_sonnet35_v2 = "claude-3-5-sonnet-v2@20241022"
    gcp_sonnet35_v2_20241022 = "claude-3-5-sonnet-v2@20241022"
    gcp_sonnet37 = "claude-3-7-sonnet@20250219"
    gcp_sonnet37_20250219 = "claude-3-7-sonnet@20250219"

    def shared_client(self) -> anthropic.AnthropicVertex:
        return _shared_client()

    def complete_with_json(
        self,
        user_messages: list[str],
        tool_model: type[ModelClass],
        *,
        system_message: str | None = None,
        client=None,
        **kwargs,
    ) -> ModelClass:
        if not client:
            client = self.shared_client()

        def create_response() -> anthropic.types.Message:
            return client.messages.create(
                model=self.value,
                max_tokens=kwargs.get("max_tokens", 2000),
                tools=[
                    {
                        "name": "return_result",
                        "description": "return the result of the task",
                        "input_schema": tool_model.model_json_schema(),
                    }
                ],
                tool_choice={"type": "tool", "name": "return_result"},
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
    prj_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not prj_id:
        raise ValueError("GOOGLE_CLOUD_PROJECT not set")
    return anthropic.AnthropicVertex(
        project_id=prj_id,
        region="us-east5",
    )


def _pick_args(kwargs: dict, keys: list[str]) -> dict:
    return {k: kwargs[k] for k in keys if k in kwargs}
