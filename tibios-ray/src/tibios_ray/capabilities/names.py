"""Capability naming vocabulary (`capability-registry` spec).

`CapabilityName` wraps a dot-separated capability string, e.g.
`"chat.generate"`, `"embedding.generate"`, `"rerank.documents"`,
`"vision.understand"`, `"speech.transcribe"` / `"speech.synthesize"`,
`"ocr.extract"`. Shape is validated **generically** — lowercase
snake_case segments joined by dots, at least one dot — deliberately NOT
a closed enum of the current six Capability Providers: Phase 2 (which
builds those Providers) does not exist yet, and `proposal.md`'s "Design
Principle: Capability-First, Not Model-Pinned" states capabilities are
organized by capability string, open-ended, so a new capability can be
introduced without touching this module.
"""

import re
from dataclasses import dataclass

_SEGMENT = r"[a-z][a-z0-9_]*"
_CAPABILITY_NAME_PATTERN = re.compile(rf"^{_SEGMENT}(\.{_SEGMENT})+$")


@dataclass(frozen=True, slots=True)
class CapabilityName:
    """A validated, dot-separated capability identifier.

    Shape: two or more lowercase snake_case segments (`[a-z][a-z0-9_]*`)
    joined by `.`, e.g. `chat.generate`. No uppercase, no whitespace, no
    empty segments, no non-dot separators."""

    value: str

    def __post_init__(self) -> None:
        if not _CAPABILITY_NAME_PATTERN.fullmatch(self.value):
            raise ValueError(
                "CapabilityName must be two or more dot-separated lowercase "
                f"snake_case segments (e.g. 'chat.generate'), got {self.value!r}"
            )
