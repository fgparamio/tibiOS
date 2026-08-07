"""Version-independent companion to the byte-identical drift guard
(`test_proto_drift.py`), per `design.md` D11 "Second guard":

Byte-identity is sensitive to the `grpcio-tools`/`protobuf` version —
the generated code embeds a runtime-version check (`_runtime_version.
ValidateProtobufRuntimeVersion(...)`) that changes on every toolchain
bump, which would redden the drift guard for a reason unrelated to
`../proto` actually changing. This guard instead reads the generated
descriptors directly and asserts their *shape*, which a toolchain bump
does not touch: `WorkerExecution` exposes exactly the three RPCs the
`worker-grpc-transport` spec names, and `ExecutionContext` carries
exactly its eight wire-visible fields (`design.md` D8).
"""

from tibios_ray.transport._generated.tibios.worker.v1 import worker_pb2


def test_worker_execution_service_has_exactly_three_rpcs() -> None:
    service = worker_pb2.DESCRIPTOR.services_by_name["WorkerExecution"]

    method_names = [method.name for method in service.methods]

    assert method_names == ["SubmitJob", "Cancel", "Pulse"]


def test_execution_context_has_exactly_eight_fields() -> None:
    descriptor = worker_pb2.ExecutionContext.DESCRIPTOR

    field_names = {field.name for field in descriptor.fields}

    assert field_names == {
        "workload_id",
        "allocation_id",
        "allocation_contract",
        "dependencies",
        "security_context",
        "observability_context",
        "execution_parameters",
        "worker_capability",
    }
    assert len(descriptor.fields) == 8
