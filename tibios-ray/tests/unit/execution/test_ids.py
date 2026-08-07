"""Tests for `tibios_ray.execution.ids` — identity value types.

`ObjectId`/`ObjectVersion`/`ContentHash`/`WorkloadId`/`AllocationId` are
frozen dataclasses, not `NewType[str]` aliases (design decision D3): a
plain string must never be usable in place of a resolved identity.

`WorkloadId`/`AllocationId`'s static half of "type-distinct from raw
strings" (`execution-identity` spec) lives in
`tests/unit/execution/pyright_fixtures/rejects_raw_string_for_workload_id.py`;
the runtime half lives here.
"""

import dataclasses

import pytest

from tibios_ray.execution.ids import AllocationId, ContentHash, ObjectId, ObjectVersion, WorkloadId


class TestObjectId:
    def test_holds_its_value(self) -> None:
        assert ObjectId("01J0000000000000000000000").value == "01J0000000000000000000000"

    def test_is_frozen(self) -> None:
        object_id = ObjectId("01J0000000000000000000000")
        with pytest.raises(dataclasses.FrozenInstanceError):
            object_id.value = "mutated"  # type: ignore[misc]

    def test_equality_is_by_value(self) -> None:
        assert ObjectId("same") == ObjectId("same")
        assert ObjectId("a") != ObjectId("b")

    def test_is_not_equal_to_a_plain_string(self) -> None:
        # Structural proof that ObjectId is type-distinct from `str` —
        # a `NewType[str]` would make this comparison misleadingly pass
        # `isinstance` checks against `str` too. A dataclass never does.
        assert not isinstance(ObjectId("deepseek"), str)


class TestObjectVersion:
    def test_holds_its_value(self) -> None:
        assert ObjectVersion(18).value == 18

    def test_is_frozen(self) -> None:
        version = ObjectVersion(1)
        with pytest.raises(dataclasses.FrozenInstanceError):
            version.value = 2  # type: ignore[misc]

    def test_equality_is_by_value(self) -> None:
        assert ObjectVersion(1) == ObjectVersion(1)
        assert ObjectVersion(1) != ObjectVersion(2)


class TestContentHash:
    def test_holds_its_value(self) -> None:
        digest = "sha256:af2398..."
        assert ContentHash(digest).value == digest

    def test_is_frozen(self) -> None:
        content_hash = ContentHash("sha256:af2398...")
        with pytest.raises(dataclasses.FrozenInstanceError):
            content_hash.value = "sha256:other"  # type: ignore[misc]

    def test_equality_is_by_value(self) -> None:
        assert ContentHash("sha256:same") == ContentHash("sha256:same")
        assert ContentHash("sha256:a") != ContentHash("sha256:b")

    def test_is_not_equal_to_a_plain_string(self) -> None:
        assert not isinstance(ContentHash("sha256:af2398..."), str)


class TestWorkloadId:
    def test_holds_its_value(self) -> None:
        assert WorkloadId("01J0000000000000000000000").value == "01J0000000000000000000000"

    def test_is_frozen(self) -> None:
        workload_id = WorkloadId("01J0000000000000000000000")
        with pytest.raises(dataclasses.FrozenInstanceError):
            workload_id.value = "mutated"  # type: ignore[misc]

    def test_equality_is_by_value(self) -> None:
        assert WorkloadId("same") == WorkloadId("same")
        assert WorkloadId("a") != WorkloadId("b")

    def test_is_not_equal_to_a_plain_string(self) -> None:
        # Structural proof that WorkloadId is type-distinct from `str` —
        # a `NewType[str]` would make this comparison misleadingly pass
        # `isinstance` checks against `str` too. A dataclass never does.
        assert not isinstance(WorkloadId("01J0000000000000000000000"), str)


class TestAllocationId:
    def test_holds_its_value(self) -> None:
        assert AllocationId("01J0000000000000000000001").value == "01J0000000000000000000001"

    def test_is_frozen(self) -> None:
        allocation_id = AllocationId("01J0000000000000000000001")
        with pytest.raises(dataclasses.FrozenInstanceError):
            allocation_id.value = "mutated"  # type: ignore[misc]

    def test_equality_is_by_value(self) -> None:
        assert AllocationId("same") == AllocationId("same")
        assert AllocationId("a") != AllocationId("b")

    def test_is_not_equal_to_a_plain_string(self) -> None:
        assert not isinstance(AllocationId("01J0000000000000000000001"), str)
