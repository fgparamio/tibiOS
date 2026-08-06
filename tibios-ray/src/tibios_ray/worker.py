"""Composition root for the tibios-ray Worker Contract entity.

This is the single place inside tibios-ray where "Worker" refers to the
entity seen by tibios-core's Runtime over gRPC (per
``../tibios-core/docs/architecture/18-worker-model.md``). It will build a
``CapabilityRegistry``, own one ``WorkerRuntime``, and dispatch each
Execution Context to the registered Capability Provider that matches its
capability — never to a "Worker" internally. See the ``ray-worker-runtime``
design (``openspec/changes/ray-worker-runtime/design.md``) for the Worker
Runtime / Capability Registry / Capability Provider contracts this module
will compose once implemented. Placeholder only — zero business logic.
"""
