"""Worker Contract vocabulary: ``ExecutionContext``, ``ExecutionChannel``,
``ExecutionEvent``, ``ExecutionReport``, ``ExecutionPulse``.

See ``../tibios-core/docs/architecture/18-worker-model.md`` and
``openspec/changes/ray-worker-runtime/design.md``.

This package has zero dependencies on any other ``tibios_ray`` package —
it is the foundation every other layer (``runtime/``, ``capabilities/``,
``selection/``, ``backends/``) depends on, never the reverse.
"""
