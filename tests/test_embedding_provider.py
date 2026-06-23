from yc_agents.rag.embeddings import (
    APIEmbeddingProvider,
    DeterministicEmbeddingProvider,
    LocalEmbeddingProviderConfig,
    LocalHTTPEmbeddingProvider,
)


def test_deterministic_embedding_provider_returns_vectors():
    provider = DeterministicEmbeddingProvider(dimensions=4)

    vectors = provider.embed(["研究背景", "技术路线"])

    assert len(vectors) == 2
    assert len(vectors[0]) == 4
    assert vectors[0] != vectors[1]


def test_local_embedding_provider_config_defaults():
    config = LocalEmbeddingProviderConfig(base_url="http://localhost:8000")

    assert config.base_url == "http://localhost:8000"
    assert config.endpoint == "/embeddings"


def test_api_embedding_provider_uses_injected_client():
    class Embeddings:
        def create(self, model, input):
            assert model == "demo-model"
            assert input == ["研究背景"]

            class Item:
                embedding = [0.1, 0.2]

            class Response:
                data = [Item()]

            return Response()

    class Client:
        embeddings = Embeddings()

    provider = APIEmbeddingProvider(Client(), model="demo-model")

    assert provider.embed(["研究背景"]) == [[0.1, 0.2]]


def test_local_http_embedding_provider_uses_injected_client():
    class Response:
        def json(self):
            return {"data": [{"embedding": [0.3, 0.4]}]}

    class Client:
        def post(self, url, json):
            assert url == "http://localhost:8000/embeddings"
            assert json == {"input": ["技术路线"]}
            return Response()

    config = LocalEmbeddingProviderConfig(base_url="http://localhost:8000")
    provider = LocalHTTPEmbeddingProvider(Client(), config)

    assert provider.embed(["技术路线"]) == [[0.3, 0.4]]
