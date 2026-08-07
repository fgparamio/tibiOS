import datetime

from tibios_ray.transport._generated.tibios.primitives.v1 import identity_pb2 as _identity_pb2
from google.protobuf import duration_pb2 as _duration_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ExecutionPhase(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    EXECUTION_PHASE_UNSPECIFIED: _ClassVar[ExecutionPhase]
    EXECUTION_PHASE_RECEIVED: _ClassVar[ExecutionPhase]
    EXECUTION_PHASE_PREPARED: _ClassVar[ExecutionPhase]
    EXECUTION_PHASE_RUNNING: _ClassVar[ExecutionPhase]
    EXECUTION_PHASE_COMPLETED: _ClassVar[ExecutionPhase]
    EXECUTION_PHASE_FAILED: _ClassVar[ExecutionPhase]
    EXECUTION_PHASE_CANCELLED: _ClassVar[ExecutionPhase]
EXECUTION_PHASE_UNSPECIFIED: ExecutionPhase
EXECUTION_PHASE_RECEIVED: ExecutionPhase
EXECUTION_PHASE_PREPARED: ExecutionPhase
EXECUTION_PHASE_RUNNING: ExecutionPhase
EXECUTION_PHASE_COMPLETED: ExecutionPhase
EXECUTION_PHASE_FAILED: ExecutionPhase
EXECUTION_PHASE_CANCELLED: ExecutionPhase

class ResolvedModelRef(_message.Message):
    __slots__ = ("object_id", "object_version", "content_hash")
    OBJECT_ID_FIELD_NUMBER: _ClassVar[int]
    OBJECT_VERSION_FIELD_NUMBER: _ClassVar[int]
    CONTENT_HASH_FIELD_NUMBER: _ClassVar[int]
    object_id: _identity_pb2.ObjectId
    object_version: _identity_pb2.ObjectVersion
    content_hash: _identity_pb2.ContentHash
    def __init__(self, object_id: _Optional[_Union[_identity_pb2.ObjectId, _Mapping]] = ..., object_version: _Optional[_Union[_identity_pb2.ObjectVersion, _Mapping]] = ..., content_hash: _Optional[_Union[_identity_pb2.ContentHash, _Mapping]] = ...) -> None: ...

class AllocationContract(_message.Message):
    __slots__ = ("max_execution_duration",)
    MAX_EXECUTION_DURATION_FIELD_NUMBER: _ClassVar[int]
    max_execution_duration: _duration_pb2.Duration
    def __init__(self, max_execution_duration: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ...) -> None: ...

class SecurityContext(_message.Message):
    __slots__ = ("tenant_id", "principal_id", "grant_scope")
    TENANT_ID_FIELD_NUMBER: _ClassVar[int]
    PRINCIPAL_ID_FIELD_NUMBER: _ClassVar[int]
    GRANT_SCOPE_FIELD_NUMBER: _ClassVar[int]
    tenant_id: str
    principal_id: str
    grant_scope: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, tenant_id: _Optional[str] = ..., principal_id: _Optional[str] = ..., grant_scope: _Optional[_Iterable[str]] = ...) -> None: ...

class ObservabilityContext(_message.Message):
    __slots__ = ("trace_id", "span_id")
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    SPAN_ID_FIELD_NUMBER: _ClassVar[int]
    trace_id: str
    span_id: str
    def __init__(self, trace_id: _Optional[str] = ..., span_id: _Optional[str] = ...) -> None: ...

class WorkerCapability(_message.Message):
    __slots__ = ("value",)
    VALUE_FIELD_NUMBER: _ClassVar[int]
    value: str
    def __init__(self, value: _Optional[str] = ...) -> None: ...

class ExecutionContext(_message.Message):
    __slots__ = ("workload_id", "allocation_id", "allocation_contract", "dependencies", "security_context", "observability_context", "execution_parameters", "worker_capability")
    class ExecutionParametersEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    WORKLOAD_ID_FIELD_NUMBER: _ClassVar[int]
    ALLOCATION_ID_FIELD_NUMBER: _ClassVar[int]
    ALLOCATION_CONTRACT_FIELD_NUMBER: _ClassVar[int]
    DEPENDENCIES_FIELD_NUMBER: _ClassVar[int]
    SECURITY_CONTEXT_FIELD_NUMBER: _ClassVar[int]
    OBSERVABILITY_CONTEXT_FIELD_NUMBER: _ClassVar[int]
    EXECUTION_PARAMETERS_FIELD_NUMBER: _ClassVar[int]
    WORKER_CAPABILITY_FIELD_NUMBER: _ClassVar[int]
    workload_id: _identity_pb2.WorkloadId
    allocation_id: _identity_pb2.AllocationId
    allocation_contract: AllocationContract
    dependencies: _containers.RepeatedCompositeFieldContainer[ResolvedModelRef]
    security_context: SecurityContext
    observability_context: ObservabilityContext
    execution_parameters: _containers.ScalarMap[str, str]
    worker_capability: WorkerCapability
    def __init__(self, workload_id: _Optional[_Union[_identity_pb2.WorkloadId, _Mapping]] = ..., allocation_id: _Optional[_Union[_identity_pb2.AllocationId, _Mapping]] = ..., allocation_contract: _Optional[_Union[AllocationContract, _Mapping]] = ..., dependencies: _Optional[_Iterable[_Union[ResolvedModelRef, _Mapping]]] = ..., security_context: _Optional[_Union[SecurityContext, _Mapping]] = ..., observability_context: _Optional[_Union[ObservabilityContext, _Mapping]] = ..., execution_parameters: _Optional[_Mapping[str, str]] = ..., worker_capability: _Optional[_Union[WorkerCapability, _Mapping]] = ...) -> None: ...

class OutputChunk(_message.Message):
    __slots__ = ("data", "sequence")
    DATA_FIELD_NUMBER: _ClassVar[int]
    SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    data: bytes
    sequence: int
    def __init__(self, data: _Optional[bytes] = ..., sequence: _Optional[int] = ...) -> None: ...

class Progress(_message.Message):
    __slots__ = ("fraction_complete", "message")
    FRACTION_COMPLETE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    fraction_complete: float
    message: str
    def __init__(self, fraction_complete: _Optional[float] = ..., message: _Optional[str] = ...) -> None: ...

class Warning(_message.Message):
    __slots__ = ("message",)
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    message: str
    def __init__(self, message: _Optional[str] = ...) -> None: ...

class CheckpointCreated(_message.Message):
    __slots__ = ("checkpoint_object_id",)
    CHECKPOINT_OBJECT_ID_FIELD_NUMBER: _ClassVar[int]
    checkpoint_object_id: _identity_pb2.ObjectId
    def __init__(self, checkpoint_object_id: _Optional[_Union[_identity_pb2.ObjectId, _Mapping]] = ...) -> None: ...

class MetricsSnapshot(_message.Message):
    __slots__ = ("metrics",)
    class MetricsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: float
        def __init__(self, key: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...
    METRICS_FIELD_NUMBER: _ClassVar[int]
    metrics: _containers.ScalarMap[str, float]
    def __init__(self, metrics: _Optional[_Mapping[str, float]] = ...) -> None: ...

class EndOfStream(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ExecutionEvent(_message.Message):
    __slots__ = ("output_chunk", "progress", "warning", "checkpoint_created", "metrics_snapshot", "end_of_stream")
    OUTPUT_CHUNK_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    WARNING_FIELD_NUMBER: _ClassVar[int]
    CHECKPOINT_CREATED_FIELD_NUMBER: _ClassVar[int]
    METRICS_SNAPSHOT_FIELD_NUMBER: _ClassVar[int]
    END_OF_STREAM_FIELD_NUMBER: _ClassVar[int]
    output_chunk: OutputChunk
    progress: Progress
    warning: Warning
    checkpoint_created: CheckpointCreated
    metrics_snapshot: MetricsSnapshot
    end_of_stream: EndOfStream
    def __init__(self, output_chunk: _Optional[_Union[OutputChunk, _Mapping]] = ..., progress: _Optional[_Union[Progress, _Mapping]] = ..., warning: _Optional[_Union[Warning, _Mapping]] = ..., checkpoint_created: _Optional[_Union[CheckpointCreated, _Mapping]] = ..., metrics_snapshot: _Optional[_Union[MetricsSnapshot, _Mapping]] = ..., end_of_stream: _Optional[_Union[EndOfStream, _Mapping]] = ...) -> None: ...

class ExecutionReport(_message.Message):
    __slots__ = ("final_phase", "duration", "trace_id", "summary")
    FINAL_PHASE_FIELD_NUMBER: _ClassVar[int]
    DURATION_FIELD_NUMBER: _ClassVar[int]
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    SUMMARY_FIELD_NUMBER: _ClassVar[int]
    final_phase: ExecutionPhase
    duration: _duration_pb2.Duration
    trace_id: str
    summary: str
    def __init__(self, final_phase: _Optional[_Union[ExecutionPhase, str]] = ..., duration: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ..., trace_id: _Optional[str] = ..., summary: _Optional[str] = ...) -> None: ...

class ExecutionPulse(_message.Message):
    __slots__ = ("phase", "healthy")
    PHASE_FIELD_NUMBER: _ClassVar[int]
    HEALTHY_FIELD_NUMBER: _ClassVar[int]
    phase: ExecutionPhase
    healthy: bool
    def __init__(self, phase: _Optional[_Union[ExecutionPhase, str]] = ..., healthy: _Optional[bool] = ...) -> None: ...

class ExecutionResponse(_message.Message):
    __slots__ = ("event", "report")
    EVENT_FIELD_NUMBER: _ClassVar[int]
    REPORT_FIELD_NUMBER: _ClassVar[int]
    event: ExecutionEvent
    report: ExecutionReport
    def __init__(self, event: _Optional[_Union[ExecutionEvent, _Mapping]] = ..., report: _Optional[_Union[ExecutionReport, _Mapping]] = ...) -> None: ...

class CancelRequest(_message.Message):
    __slots__ = ("workload_id",)
    WORKLOAD_ID_FIELD_NUMBER: _ClassVar[int]
    workload_id: _identity_pb2.WorkloadId
    def __init__(self, workload_id: _Optional[_Union[_identity_pb2.WorkloadId, _Mapping]] = ...) -> None: ...

class PulseRequest(_message.Message):
    __slots__ = ("workload_id",)
    WORKLOAD_ID_FIELD_NUMBER: _ClassVar[int]
    workload_id: _identity_pb2.WorkloadId
    def __init__(self, workload_id: _Optional[_Union[_identity_pb2.WorkloadId, _Mapping]] = ...) -> None: ...

class CancelAck(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
