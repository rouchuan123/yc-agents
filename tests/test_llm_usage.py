import httpx
from openai import APIStatusError

from yc_agents.core.config import ProviderConfig
from yc_agents.core.llm import YCAgentsLLM


class Completions:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class Client:
    def __init__(self, response):
        self.chat = type("Chat", (), {"completions": Completions(response)})()


def config():
    return ProviderConfig("test", "model", "key", "https://example.test")


def test_non_stream_response_records_provider_usage():
    usage = type("Usage", (), {"prompt_tokens": 9000, "completion_tokens": 200, "total_tokens": 9200})()
    message = type("Message", (), {"content": "ok"})()
    response = type("Response", (), {"choices": [type("Choice", (), {"message": message})()], "usage": usage})()
    llm = YCAgentsLLM(config=config(), client=Client(response))

    assert llm.think([{"role": "user", "content": "hello"}]) == "ok"
    assert llm.usage_ledger.current_context.total_tokens == 9200
    assert llm.usage_ledger.current_context.source == "provider"


def test_missing_usage_records_marked_estimate():
    message = type("Message", (), {"content": "answer"})()
    response = type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()
    llm = YCAgentsLLM(config=config(), client=Client(response))

    llm.think([{"role": "user", "content": "hello"}])

    assert llm.usage_ledger.current_context.source == "estimated"
    assert llm.usage_ledger.current_context.total_tokens > 0


def test_stream_usage_only_chunk_is_recorded():
    delta = lambda content: type("Chunk", (), {"choices": [type("Choice", (), {"delta": type("Delta", (), {"content": content})()})()], "usage": None})()
    usage = type("Usage", (), {"prompt_tokens": 8000, "completion_tokens": 100, "total_tokens": 8100})()
    usage_chunk = type("Chunk", (), {"choices": [], "usage": usage})()
    client = Client(iter([delta("hello"), usage_chunk]))
    llm = YCAgentsLLM(config=config(), client=client)

    assert list(llm.stream_think([{"role": "user", "content": "hi"}])) == ["hello"]
    assert llm.usage_ledger.current_context.total_tokens == 8100
    assert client.chat.completions.calls[0]["stream_options"] == {"include_usage": True}


def test_auxiliary_llm_call_does_not_replace_primary_context():
    usage = type("Usage", (), {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110})()
    message = type("Message", (), {"content": "ok"})()
    response = type("Response", (), {"choices": [type("Choice", (), {"message": message})()], "usage": usage})()
    llm = YCAgentsLLM(config=config(), client=Client(response))
    llm.think([{"role": "user", "content": "main"}])
    llm.think([{"role": "user", "content": "side"}], usage_kind="auxiliary")

    assert llm.usage_ledger.current_context.total_tokens == 110
    assert llm.usage_ledger.primary_calls == 1
    assert llm.usage_ledger.auxiliary_calls == 1


def test_stream_retries_once_when_provider_rejects_usage_option():
    chunk = type(
        "Chunk",
        (),
        {
            "choices": [
                type(
                    "Choice",
                    (),
                    {"delta": type("Delta", (), {"content": "ok"})()},
                )()
            ],
            "usage": None,
        },
    )()

    class RejectingCompletions:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            if "stream_options" in kwargs:
                request = httpx.Request("POST", "https://example.test/chat/completions")
                response = httpx.Response(400, request=request)
                raise APIStatusError(
                    "Unsupported parameter: stream_options",
                    response=response,
                    body={"error": {"message": "stream_options is unsupported"}},
                )
            return iter([chunk])

    completions = RejectingCompletions()
    client = type(
        "Client",
        (),
        {"chat": type("Chat", (), {"completions": completions})()},
    )()
    llm = YCAgentsLLM(config=config(), client=client)

    assert list(llm.stream_think([{"role": "user", "content": "hi"}])) == ["ok"]
    assert len(completions.calls) == 2
    assert "stream_options" not in completions.calls[1]
    assert llm.usage_ledger.current_context.source == "estimated"
