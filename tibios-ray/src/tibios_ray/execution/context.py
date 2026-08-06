"""Execution Context vocabulary — the immutable bundle a Capability
Provider receives to execute one unit of work (``18-worker-model.md``).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

from tibios_ray.execution.channel import CancellationToken, ExecutionChannel
from tibios_ray.execution.ids import ContentHash, ObjectId, ObjectVersion


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolvedModelRef:
    """A Model dependency reference already resolved by the Runtime.

    Constructible only from already-typed `ObjectId`/`ObjectVersion`/
    `ContentHash` values — never from a raw family string such as
    ``"deepseek"``. In practice the only legitimate source of a
    `ResolvedModelRef` is `ExecutionContext.dependencies`, populated by
    the Runtime before an execution starts (``18-worker-model.md``:
    "Dependency References already resolved — Workers never locate
    Objects or perform scheduling-time discovery").
    """

    object_id: ObjectId
    version: ObjectVersion
    content_hash: ContentHash

    def __post_init__(self) -> None:
        if not isinstance(self.object_id, ObjectId):
            raise TypeError(
                "ResolvedModelRef.object_id must be an ObjectId, "
                f"got {type(self.object_id).__name__}"
            )
        if not isinstance(self.version, ObjectVersion):
            raise TypeError(
                "ResolvedModelRef.version must be an ObjectVersion, "
                f"got {type(self.version).__name__}"
            )
        if not isinstance(self.content_hash, ContentHash):
            raise TypeError(
                "ResolvedModelRef.content_hash must be a ContentHash, "
                f"got {type(self.content_hash).__name__}"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class AllocationContract:
    """Immutable execution constraints a Capability Provider honors —
    never creates, modifies, or renews (``18-worker-model.md`` /
    ``15-allocation-model.md``)."""

    exclusive: bool
    renewable_lease: bool
    preemptible: bool
    migration_allowed: bool
    checkpoint_required: bool
    max_execution_duration: timedelta


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionContext:
    """Everything required to execute one unit of work, created by the
    Runtime and immutable thereafter (``18-worker-model.md``)."""

    capability: str
    allocation_contract: AllocationContract
    dependencies: Mapping[str, ResolvedModelRef]
    channel: ExecutionChannel
    cancellation: CancellationToken
