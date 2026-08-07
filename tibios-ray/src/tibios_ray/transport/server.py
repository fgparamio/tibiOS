"""`serve()` — builds and runs the `WorkerExecution` gRPC server.

Together with `servicer.py`, the only two modules outside
`transport/_generated/` allowed to import `grpc` or a `_pb2` symbol
(design decision D13). The server is created and served **on the same
event loop that calls `serve()`** (design decision D12) — no cross-loop
handoff, no background thread owning the server.
"""

import grpc

from tibios_ray.runtime.worker_runtime import WorkerRuntime
from tibios_ray.transport._generated.tibios.worker.v1 import worker_pb2_grpc
from tibios_ray.transport.servicer import WorkerExecutionServicer


async def serve(runtime: WorkerRuntime, address: str) -> None:
    """Builds a `grpc.aio.server()`, registers `WorkerExecutionServicer`
    bound to `runtime`, binds `address`, and serves until cancelled."""
    server = grpc.aio.server()
    worker_pb2_grpc.add_WorkerExecutionServicer_to_server(
        WorkerExecutionServicer(runtime), server
    )
    server.add_insecure_port(address)
    await server.start()
    await server.wait_for_termination()
