"""The gRPC boundary: the only package in tibios-ray allowed to import
`grpc` or any `_pb2`/`_pb2_grpc` symbol (`worker-grpc-transport` spec,
Requirement "Generated Code Is Isolated To The Transport Package";
`design.md` D13).

`_generated/` holds the checked-in output of `scripts/generate_proto.py`
(D11) and is never hand-edited. The rest of this package — conversion,
errors, cancellation, the servicer — lands in later slices (S3/S4a/S4b)
and is re-exported here as it arrives.
"""

from tibios_ray.transport.server import serve

__all__ = ["serve"]
