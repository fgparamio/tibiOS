"""gRPC Worker Contract process entry point.

Implements the Worker Contract defined in
``../tibios-core/docs/architecture/18-worker-model.md`` (tag
``architecture-v1.0``) and projected onto the wire by
``../proto/tibios/worker/v1/worker.proto``. This module is the process
entry point only — it composes ``worker.build_runtime()`` with
``transport.serve()`` and imports **no** `grpc`/`_pb2` symbol itself
(design decision D13); the gRPC transport lives entirely in ``transport/``.
"""

import asyncio
import os

from tibios_ray import transport, worker

DEFAULT_ADDRESS = "[::]:50051"


async def _serve() -> None:
    address = os.environ.get("TIBIOS_RAY_ADDRESS", DEFAULT_ADDRESS)
    await transport.serve(worker.build_runtime(), address)


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
