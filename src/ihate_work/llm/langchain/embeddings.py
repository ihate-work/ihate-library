import os
from enum import StrEnum

from langchain_core.embeddings import Embeddings

try:
    from langchain_ollama.embeddings import OllamaEmbeddings
except ImportError:
    OllamaEmbeddings = None

# from langchain_community.storage.redis import RedisStore
# from langchain_community.storage.sql import SQLStore


class EmbeddingModel(StrEnum):
    granite_embedding_278m = "granite-embedding:278m"  # multilingual, dim=768
    paraphrase_multilingual = "paraphrase-multilingual:278m"  # multilingual, long-context capable, dim=768
    mxbai_embed_large = "mxbai-embed-large"  # eng only, dim=1024

    def to_embedding(self, *, base_url=None, **kwargs) -> Embeddings:
        if self in [
            self.granite_embedding_278m,
            self.paraphrase_multilingual,
            self.mxbai_embed_large,
        ]:
            if not base_url:
                base_url = os.getenv("OLLAMA_BASE_URL", None)
            assert base_url, "OLLAMA_BASE_URL not found"
            return OllamaEmbeddings(model=self.value, base_url=base_url, **kwargs)
        assert False, f"Model {self} not supported"

    @property
    def dim(self) -> int:
        if self in [self.granite_embedding_278m, self.paraphrase_multilingual]:
            return 768
        elif self == self.mxbai_embed_large:
            return 1024
        assert False, f"Model {self} not supported"
