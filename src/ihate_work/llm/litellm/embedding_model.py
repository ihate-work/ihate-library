import os
from enum import StrEnum
from typing import TYPE_CHECKING, TypedDict, Unpack

if TYPE_CHECKING:
    pass


class EmbeddingParams(TypedDict, total=False):
    ollama_base_url: str


class EmbeddingApi:
    def embedder_name(self) -> str: ...
    def embedder_dim(self) -> int: ...
    def embed_text(
        self, text: str, **kwargs: Unpack[EmbeddingParams]
    ) -> list[float]: ...
    def embed_texts(
        self, texts: list[str], **kwargs: Unpack[EmbeddingParams]
    ) -> list[list[float]]: ...


class EmbeddingModels(EmbeddingApi, StrEnum):
    granite_embedding_278m = "ollama/granite-embedding:278m"  # multilingual, dim=768
    paraphrase_multilingual = "ollama/paraphrase-multilingual:278m"  # multilingual, long-context capable, dim=768
    mxbai_embed_large = "ollama/mxbai-embed-large"  # eng only, dim=1024
    embeddinggemma_300m = "ollama/embeddinggemma:300m"  # multilingual, 2k ctx, dim=768

    def embedder_name(self) -> str:
        return self.value

    def embedder_dim(self) -> int:
        if self in [self.granite_embedding_278m, self.paraphrase_multilingual, self.embeddinggemma_300m]:
            return 768
        elif self == self.mxbai_embed_large:
            return 1024
        raise NotImplementedError(f"Model {self} not supported")

    def embed_text(self, text: str, **kwargs: Unpack[EmbeddingParams]) -> list[float]:
        import litellm
        api_base = kwargs.get("ollama_base_url") or os.getenv("OLLAMA_BASE_URL")
        response = litellm.embedding(model=self.value, input=[text], api_base=api_base)
        return response.data[0]["embedding"]

    def embed_texts(
        self, texts: list[str], **kwargs: Unpack[EmbeddingParams]
    ) -> list[list[float]]:
        import litellm
        api_base = kwargs.get("ollama_base_url") or os.getenv("OLLAMA_BASE_URL")
        response = litellm.embedding(model=self.value, input=texts, api_base=api_base)
        return [item["embedding"] for item in response.data]
