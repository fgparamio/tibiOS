"""Composition root for the tibios-ray Worker Contract entity.

This is the single place inside tibios-ray where "Worker" refers to the
entity seen by tibios-core's Runtime over gRPC (per
``../tibios-core/docs/architecture/18-worker-model.md``). It builds a
:class:`tibios_ray.runtime.registry.CapabilityRegistry` from the set of
registered Capability Providers and owns exactly one
:class:`tibios_ray.runtime.worker_runtime.WorkerRuntime`, then dispatches
each incoming Execution Context to the registered Capability Provider that
matches its capability — never to a "Worker" internally. Both types are
real, implemented contracts as of the ``ray-worker-runtime`` change
(``openspec/changes/ray-worker-runtime/design.md``, Phases 4-5), not
placeholders; only the composition performed *here* — instantiating a
``CapabilityRegistry`` with the concrete Capability Providers and handing
it to a ``WorkerRuntime`` — remains to be written.

That composition, and the gRPC transport that will call into it, are
blocked on the shared ``.proto`` Worker Contract definition, which does
not yet exist in this repo (proposed shared location: ``../TibiOS/proto/``,
see ``server.py``). A sibling change, ``proto-worker-contract``, is in
progress in ``tibios-core`` as of this writing to define that contract; this
module intentionally does not anticipate its shape. Placeholder only —
zero business logic.
"""
