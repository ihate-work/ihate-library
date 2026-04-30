from typing import TypeVar, cast

import litellm
from litellm.types.utils import ModelResponse

M = TypeVar("M")


class ChatCompModel:
    def __init__(self, model: str):
        self.__model = model

    def completion_single(
        self,
        *,
        messages: list[str | dict],
        cast_: type[M] = str,
        # num of choices
        n=1,
        # sampling
        temperature: float | None = None,
        top_p: float | None = None,
        # length control
        stop=None,
        max_completion_tokens: int | None = None,
        max_tokens: int | None = None,
        # tools
        tools: list["litellm.Tool"] | None = None,
    ) -> M:
        assert cast_ in (str, ModelResponse), "cast_ must be str or ModelResponse"
        (res) = litellm.completion(
            model=self.__model,
            messages=messages,
            n=n,
            temperature=temperature,
            top_p=top_p,
            stop=stop,
            max_completion_tokens=max_completion_tokens,
            max_tokens=max_tokens,
            tools=tools,
        )
        res = cast(ModelResponse, res)
        if cast_ is str:
            if isinstance(res, tuple):
                res = res[0]
            res_text = res.choices[0].message.content
            return res_text
        elif cast_ is ModelResponse:
            return res
        raise ValueError(f"Unsupported cast type: {cast_}")
