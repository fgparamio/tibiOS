"""Tests for `tibios_ray.capabilities.embedding` — the Embedding
Capability Provider (`capability-providers` spec: "Descriptor Catalog
Correctness and Stability", "Chat advertises realistic flags; Embedding/
Rerank advertise none").

Only catalog data is asserted here — one full descriptor equality plus
flag values. Structural/behavioral conformance (identity stability,
element typing, FLC shape, `execute()` always raising, end-to-end
dispatch) is covered generically by `test_provider_conformance.py`
(design decision CP7) so this file stays small.

Families here follow design.md's Family Label Convention deviations from
`proposal.md`'s shorthand: `nomic` -> `nomic_embed`, `jina` ->
`jina_embeddings` (rule 3 keeps published role tokens the FLC would
otherwise drop).
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.embedding import EMBEDDING_GENERATE_DESCRIPTOR, EmbeddingProvider
from tibios_ray.capabilities.names import CapabilityName


class TestEmbeddingProvider:
    def test_descriptor_matches_the_spec_table_exactly(self) -> None:
        provider = EmbeddingProvider()

        assert provider.descriptor == CapabilityDescriptor(
            capability=CapabilityName("embedding.generate"),
            families=frozenset(
                {
                    ModelFamily("bge"),
                    ModelFamily("nomic_embed"),
                    ModelFamily("e5"),
                    ModelFamily("jina_embeddings"),
                }
            ),
            backends=frozenset({BackendId("onnxruntime")}),
        )

    def test_descriptor_is_the_module_level_constant(self) -> None:
        provider = EmbeddingProvider()

        assert provider.descriptor is EMBEDDING_GENERATE_DESCRIPTOR

    def test_flags_are_all_false(self) -> None:
        flags = EmbeddingProvider().descriptor.flags

        assert flags == CapabilityFlags()
        assert flags.streaming is False
        assert flags.tools is False
        assert flags.json is False
        assert flags.reasoning is False
