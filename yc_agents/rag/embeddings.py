import hashlib
from dataclasses import dataclass


class EmbeddingProvider:
    def embed(self, texts):
        raise NotImplementedError


class DeterministicEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimensions=16):
        self.dimensions = dimensions

    def embed(self, texts):
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text):
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [
            digest[index % len(digest)] / 255
            for index in range(self.dimensions)
        ]


@dataclass(frozen=True)
class APIEmbeddingProviderConfig:
    model: str = "text-embedding-3-small"
    env_api_key: str = "OPENAI_API_KEY"
    env_base_url: str = "OPENAI_BASE_URL"


@dataclass(frozen=True)
class LocalEmbeddingProviderConfig:
    base_url: str
    endpoint: str = "/embeddings"


class APIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, client, model="text-embedding-3-small"):
        self.client = client
        self.model = model

    def embed(self, texts):
        response = self.client.embeddings.create(
            model=self.model,
            input=list(texts),
        )
        return [item.embedding for item in response.data]


class LocalHTTPEmbeddingProvider(EmbeddingProvider):
    def __init__(self, client, config):
        self.client = client
        self.config = config

    def embed(self, texts):
        url = self.config.base_url.rstrip("/") + self.config.endpoint
        response = self.client.post(url, json={"input": list(texts)})
        data = response.json()
        return [item["embedding"] for item in data.get("data", [])]
