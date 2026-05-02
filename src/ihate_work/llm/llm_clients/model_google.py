import functools
from enum import StrEnum

from google import genai
from google.genai import types as genai_types


class GcpGeminiBare(StrEnum):
    # more: https://cloud.google.com/vertex-ai/docs/generative-ai/models
    gemini_flash20_exp = "gemini-2.0-flash-exp"

    def complete_with_json_v0(self, user_content: str) -> list[genai_types.Candidate]:
        client = _get_client(project="vertex-ai-sandbox", location="us-central1")

        response = client.models.generate_content(model=self.value, contents=user_content)
        return response.candidates or []

    def generate_content(self, user_content: str) -> list[genai_types.Candidate]:
        pass


@functools.lru_cache(maxsize=1)
def _get_client(project: str, location: str) -> genai.Client:
    return genai.Client(vertexai=True, project=project, location=location)
