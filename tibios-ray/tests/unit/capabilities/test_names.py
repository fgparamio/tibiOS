"""Tests for `tibios_ray.capabilities.names` — `CapabilityName` shape
validation (`capability-registry` spec; `proposal.md` "Design Principle:
Capability-First, Not Model-Pinned" — capabilities are organized by
capability string, never a hardcoded enum, since Phase 2's concrete
Providers do not exist yet and the vocabulary is deliberately
open-ended).
"""

import dataclasses

import pytest

from tibios_ray.capabilities.names import CapabilityName


class TestCapabilityNameValidShapes:
    @pytest.mark.parametrize(
        "value",
        [
            "chat.generate",
            "embedding.generate",
            "rerank.documents",
            "vision.understand",
            "speech.transcribe",
            "speech.synthesize",
            "ocr.extract",
            "ocr.extract.batch",  # shape is generic: >=2 segments, not hardcoded to exactly 2
        ],
    )
    def test_accepts_dot_separated_lowercase_segments(self, value: str) -> None:
        name = CapabilityName(value)
        assert name.value == value


class TestCapabilityNameInvalidShapes:
    @pytest.mark.parametrize(
        "value",
        [
            "",
            "chat",  # no dot at all — single segment
            "chat.",  # trailing dot / empty final segment
            ".generate",  # leading dot / empty first segment
            "chat..generate",  # empty segment between dots
            "Chat.Generate",  # uppercase not allowed
            "chat generate",  # whitespace, no dot
            "chat-generate",  # hyphen is not a valid separator, no dot
            "chat.generate ",  # trailing whitespace
            "1chat.generate",  # segment must start with a lowercase letter
            "chat.1generate",  # same rule applies to every segment
        ],
    )
    def test_rejects_malformed_shapes(self, value: str) -> None:
        with pytest.raises(ValueError, match="CapabilityName"):
            CapabilityName(value)


class TestCapabilityNameValueSemantics:
    def test_is_frozen(self) -> None:
        name = CapabilityName("chat.generate")
        with pytest.raises(dataclasses.FrozenInstanceError):
            name.value = "embedding.generate"  # type: ignore[misc]

    def test_equality_and_hash_are_by_value(self) -> None:
        assert CapabilityName("chat.generate") == CapabilityName("chat.generate")
        assert CapabilityName("chat.generate") != CapabilityName("embedding.generate")
        assert hash(CapabilityName("chat.generate")) == hash(CapabilityName("chat.generate"))
