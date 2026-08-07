"""Tests for `tibios_ray.capabilities.requests` — `CapabilityRequest` and
the three concrete Requests (`design.md` D22, ADR-0004).

Table-driven over every Required/Rejected row in `design.md`'s Key
Contracts table, plus "unknown key present -> parse succeeds" for each
Request.
"""

import pytest

from tibios_ray.capabilities.errors import RequestParseError
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.capabilities.requests import ChatRequest, EmbeddingRequest, RerankRequest


class TestChatRequest:
    def test_parses_a_full_valid_payload(self) -> None:
        request = ChatRequest.parse(
            {
                "prompt": "hello",
                "max_tokens": "16",
                "temperature": "0.5",
                "stop": '["</s>", "STOP"]',
            }
        )

        assert request.prompt == "hello"
        assert request.max_tokens == 16
        assert request.temperature == 0.5
        assert request.stop == ("</s>", "STOP")

    def test_temperature_defaults_to_one(self) -> None:
        request = ChatRequest.parse({"prompt": "hello", "max_tokens": "16"})

        assert request.temperature == 1.0

    def test_stop_defaults_to_empty_tuple(self) -> None:
        request = ChatRequest.parse({"prompt": "hello", "max_tokens": "16"})

        assert request.stop == ()

    def test_unknown_key_is_ignored(self) -> None:
        request = ChatRequest.parse(
            {"prompt": "hello", "max_tokens": "16", "unrelated": "value"}
        )

        assert request.prompt == "hello"

    def test_missing_prompt_raises(self) -> None:
        with pytest.raises(RequestParseError) as excinfo:
            ChatRequest.parse({"max_tokens": "16"})

        assert excinfo.value.capability == CapabilityName("chat.generate")
        assert excinfo.value.parameter == "prompt"

    def test_empty_prompt_after_strip_raises(self) -> None:
        with pytest.raises(RequestParseError):
            ChatRequest.parse({"prompt": "   ", "max_tokens": "16"})

    def test_missing_max_tokens_raises(self) -> None:
        with pytest.raises(RequestParseError) as excinfo:
            ChatRequest.parse({"prompt": "hello"})

        assert excinfo.value.parameter == "max_tokens"

    def test_non_integer_max_tokens_raises(self) -> None:
        with pytest.raises(RequestParseError):
            ChatRequest.parse({"prompt": "hello", "max_tokens": "abc"})

    def test_zero_max_tokens_raises(self) -> None:
        with pytest.raises(RequestParseError):
            ChatRequest.parse({"prompt": "hello", "max_tokens": "0"})

    def test_negative_max_tokens_raises(self) -> None:
        with pytest.raises(RequestParseError):
            ChatRequest.parse({"prompt": "hello", "max_tokens": "-1"})

    def test_non_float_temperature_raises(self) -> None:
        with pytest.raises(RequestParseError) as excinfo:
            ChatRequest.parse({"prompt": "hello", "max_tokens": "16", "temperature": "hot"})

        assert excinfo.value.parameter == "temperature"

    def test_negative_temperature_raises(self) -> None:
        with pytest.raises(RequestParseError):
            ChatRequest.parse({"prompt": "hello", "max_tokens": "16", "temperature": "-0.1"})

    def test_invalid_json_stop_raises(self) -> None:
        with pytest.raises(RequestParseError) as excinfo:
            ChatRequest.parse({"prompt": "hello", "max_tokens": "16", "stop": "not-json"})

        assert excinfo.value.parameter == "stop"

    def test_stop_not_an_array_raises(self) -> None:
        with pytest.raises(RequestParseError):
            ChatRequest.parse({"prompt": "hello", "max_tokens": "16", "stop": '{"a": 1}'})

    def test_stop_with_non_string_element_raises(self) -> None:
        with pytest.raises(RequestParseError):
            ChatRequest.parse({"prompt": "hello", "max_tokens": "16", "stop": "[1, 2]"})


class TestEmbeddingRequest:
    def test_parses_a_valid_payload(self) -> None:
        request = EmbeddingRequest.parse({"inputs": '["a", "b"]'})

        assert request.inputs == ("a", "b")

    def test_unknown_key_is_ignored(self) -> None:
        request = EmbeddingRequest.parse({"inputs": '["a"]', "unrelated": "value"})

        assert request.inputs == ("a",)

    def test_missing_inputs_raises(self) -> None:
        with pytest.raises(RequestParseError) as excinfo:
            EmbeddingRequest.parse({})

        assert excinfo.value.capability == CapabilityName("embedding.generate")
        assert excinfo.value.parameter == "inputs"

    def test_invalid_json_inputs_raises(self) -> None:
        with pytest.raises(RequestParseError):
            EmbeddingRequest.parse({"inputs": "not-json"})

    def test_inputs_not_an_array_raises(self) -> None:
        with pytest.raises(RequestParseError):
            EmbeddingRequest.parse({"inputs": '{"a": 1}'})

    def test_empty_inputs_array_raises(self) -> None:
        with pytest.raises(RequestParseError):
            EmbeddingRequest.parse({"inputs": "[]"})

    def test_inputs_with_non_string_element_raises(self) -> None:
        with pytest.raises(RequestParseError):
            EmbeddingRequest.parse({"inputs": "[1, 2]"})


class TestRerankRequest:
    def test_parses_a_valid_payload(self) -> None:
        request = RerankRequest.parse({"query": "q", "documents": '["a", "b"]'})

        assert request.query == "q"
        assert request.documents == ("a", "b")

    def test_unknown_key_is_ignored(self) -> None:
        request = RerankRequest.parse(
            {"query": "q", "documents": '["a"]', "unrelated": "value"}
        )

        assert request.query == "q"

    def test_missing_query_raises(self) -> None:
        with pytest.raises(RequestParseError) as excinfo:
            RerankRequest.parse({"documents": '["a"]'})

        assert excinfo.value.capability == CapabilityName("rerank.documents")
        assert excinfo.value.parameter == "query"

    def test_empty_query_after_strip_raises(self) -> None:
        with pytest.raises(RequestParseError):
            RerankRequest.parse({"query": "   ", "documents": '["a"]'})

    def test_missing_documents_raises(self) -> None:
        with pytest.raises(RequestParseError) as excinfo:
            RerankRequest.parse({"query": "q"})

        assert excinfo.value.parameter == "documents"

    def test_invalid_json_documents_raises(self) -> None:
        with pytest.raises(RequestParseError):
            RerankRequest.parse({"query": "q", "documents": "not-json"})

    def test_documents_not_an_array_raises(self) -> None:
        with pytest.raises(RequestParseError):
            RerankRequest.parse({"query": "q", "documents": '{"a": 1}'})

    def test_empty_documents_array_raises(self) -> None:
        with pytest.raises(RequestParseError):
            RerankRequest.parse({"query": "q", "documents": "[]"})

    def test_documents_with_non_string_element_raises(self) -> None:
        with pytest.raises(RequestParseError):
            RerankRequest.parse({"query": "q", "documents": "[1, 2]"})
