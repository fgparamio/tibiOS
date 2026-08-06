"""Tests for `tibios_ray.capabilities.rerank` — the Rerank Capability
Provider (`capability-providers` spec: "Descriptor Catalog Correctness and
Stability", "Chat advertises realistic flags; Embedding/Rerank advertise
none").

Only catalog data is asserted here — one full descriptor equality plus
flag values. Structural/behavioral conformance (identity stability,
element typing, FLC shape, `execute()` always raising, end-to-end
dispatch) is covered generically by `test_provider_conformance.py`
(design decision CP7) so this file stays small.

Families here follow design.md's Family Label Convention: `bge_reranker`,
`jina_reranker` (rule 3 keeps the published `reranker` role token).
"""

from tibios_ray.backends.adapter import BackendId
from tibios_ray.capabilities.descriptor import CapabilityDescriptor, CapabilityFlags, ModelFamily
from tibios_ray.capabilities.names import CapabilityName
from tibios_ray.capabilities.rerank import RERANK_DOCUMENTS_DESCRIPTOR, RerankProvider


class TestRerankProvider:
    def test_descriptor_matches_the_spec_table_exactly(self) -> None:
        provider = RerankProvider()

        assert provider.descriptor == CapabilityDescriptor(
            capability=CapabilityName("rerank.documents"),
            families=frozenset(
                {
                    ModelFamily("bge_reranker"),
                    ModelFamily("jina_reranker"),
                }
            ),
            backends=frozenset({BackendId("onnxruntime")}),
        )

    def test_descriptor_is_the_module_level_constant(self) -> None:
        provider = RerankProvider()

        assert provider.descriptor is RERANK_DOCUMENTS_DESCRIPTOR

    def test_flags_are_all_false(self) -> None:
        flags = RerankProvider().descriptor.flags

        assert flags == CapabilityFlags()
        assert flags.streaming is False
        assert flags.tools is False
        assert flags.json is False
        assert flags.reasoning is False
