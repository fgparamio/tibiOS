"""Tests for `tibios_ray.worker` — the composition root.

`build_runtime()` is the single place that wires all seven Capability
Providers into one `CapabilityRegistry` and hands it to one
`WorkerRuntime`; `transport/server.py`'s `serve()` calls it, never the
other way around (design decision D13: `worker.py` imports zero `grpc`/
`_pb2` symbol — `tests/unit/transport/test_transport_isolation.py`
enforces that recursively).

Slice 7 (D29) makes `build_runtime()` a real Composition Root: it takes
an optional `WorkerConfig` (`None` -> `WorkerConfig.from_env()`),
constructs the one shared `PreferenceOrderPolicy`, builds each per-engine
Backend only when its config is present, and injects the resulting
mappings into `ChatProvider`/`EmbeddingProvider`/`RerankProvider`. Tests
below reach into `WorkerRuntime._registry` to inspect the wired
Providers' injected mappings directly — `WorkerRuntime` deliberately
exposes no public accessor for its registry (it dispatches only through
`resolve()`), and there is no other way to assert "this Provider's
mapping is empty/contains exactly this BackendId" without either a
public escape hatch nobody else needs or a full fake `ExecutionContext`
dispatch per engine. Reaching into the private attribute is a judgment
call, consistent with this suite's existing whitebox conformance checks
(e.g. `test_catalog_conformance.py`'s AST source inspection).
"""

import ast
import asyncio
import sys
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

import tibios_ray
from tibios_ray.capabilities.chat import CHAT_GENERATE_DESCRIPTOR, ChatProvider
from tibios_ray.capabilities.embedding import EMBEDDING_GENERATE_DESCRIPTOR, EmbeddingProvider
from tibios_ray.capabilities.rerank import RERANK_DOCUMENTS_DESCRIPTOR, RerankProvider
from tibios_ray.config import LlamaCppConfig, OnnxConfig, VllmConfig, WorkerConfig
from tibios_ray.engines.llamacpp import LLAMA_CPP_BACKEND_ID
from tibios_ray.engines.onnxrt import ONNXRUNTIME_BACKEND_ID
from tibios_ray.engines.vllm import VLLM_BACKEND_ID
from tibios_ray.runtime.worker_runtime import WorkerRuntime
from tibios_ray.selection.policy import Quantization, ServingPlan
from tibios_ray.worker import build_runtime

_EMPTY_CONFIG = WorkerConfig(llamacpp=None, vllm=None, onnx_embedding=None, onnx_rerank=None)


def _providers(runtime: WorkerRuntime) -> tuple[ChatProvider, EmbeddingProvider, RerankProvider]:
    """Resolve the three wired Providers out of `runtime`'s private
    registry (see module docstring). `CapabilityRegistry.resolve()`
    returns the `CapabilityProvider` Protocol, which does not declare
    `.backends` — the `cast()`s are exact, since `build_runtime()` is
    known to register exactly one `ChatProvider`/`EmbeddingProvider`/
    `RerankProvider` per capability."""
    registry = runtime._registry  # noqa: SLF001 - see module docstring
    chat = cast(ChatProvider, registry.resolve(CHAT_GENERATE_DESCRIPTOR.capability))
    embedding = cast(EmbeddingProvider, registry.resolve(EMBEDDING_GENERATE_DESCRIPTOR.capability))
    rerank = cast(RerankProvider, registry.resolve(RERANK_DOCUMENTS_DESCRIPTOR.capability))
    return chat, embedding, rerank


@pytest.fixture
def fake_llama_cpp_module():
    """Fakes `sys.modules["llama_cpp"]` so `LlamaCppTextBackend`'s real,
    unmodified `default_llama_factory` (D26/D27's eager pool
    construction) can run with zero SDK installed — the same technique
    `test_vllm_sampling_params.py` uses for `vllm.sampling_params`
    (`importlib.import_module` consults `sys.modules` first, LC11/VL8's
    seam). Yields the list of constructed `_CountingLlama` instances so a
    test can assert exactly how many (and when) `Llama(...)` was called."""
    module = ModuleType("llama_cpp")
    instances: list[object] = []

    class _CountingLlama:
        def __init__(self, *, model_path: str, verbose: bool = False) -> None:
            self.model_path = model_path
            self.verbose = verbose
            instances.append(self)

        def close(self) -> None:
            pass

    module.Llama = _CountingLlama  # type: ignore[attr-defined]
    previous = sys.modules.get("llama_cpp")
    sys.modules["llama_cpp"] = module
    try:
        yield instances
    finally:
        if previous is None:
            del sys.modules["llama_cpp"]
        else:
            sys.modules["llama_cpp"] = previous


def test_build_runtime_returns_a_worker_runtime() -> None:
    runtime = build_runtime()
    assert isinstance(runtime, WorkerRuntime)


def test_build_runtime_is_callable_repeatedly_with_independent_registries() -> None:
    # No shared mutable state across composition roots (D6: immutable,
    # ctor-built registry — no global singleton).
    assert build_runtime() is not build_runtime()


def test_zero_configuration_wires_empty_mappings_for_every_wired_provider() -> None:
    # `worker-configuration` spec: "Worker starts with zero configuration
    # present" — build_runtime() must not raise, and every wired
    # Provider's mapping must be empty (no fabricated backend).
    runtime = build_runtime(_EMPTY_CONFIG)

    chat, embedding, rerank = _providers(runtime)

    assert dict(chat.backends) == {}
    assert dict(embedding.backends) == {}
    assert dict(rerank.backends) == {}


def test_only_vllm_configured_wires_only_the_chat_provider() -> None:
    # `worker-configuration` spec: "A partially configured deployment
    # wires only the configured engines". vLLM's Backend performs no SDK
    # work at construction time (VL2, lazy init) so this needs no fake
    # module.
    config = WorkerConfig(
        llamacpp=None,
        vllm=VllmConfig(model="m"),
        onnx_embedding=None,
        onnx_rerank=None,
    )

    runtime = build_runtime(config)
    chat, embedding, rerank = _providers(runtime)

    assert set(chat.backends) == {VLLM_BACKEND_ID}
    assert dict(embedding.backends) == {}
    assert dict(rerank.backends) == {}


def test_only_onnx_embedding_configured_wires_only_the_embedding_provider() -> None:
    # OnnxEmbeddingBackend also performs no SDK work at construction
    # time (OR2, lazy init), so a real (nonexistent) path is enough.
    config = WorkerConfig(
        llamacpp=None,
        vllm=None,
        onnx_embedding=OnnxConfig(model_path="model.onnx", tokenizer_path="tokenizer.json"),
        onnx_rerank=None,
    )

    runtime = build_runtime(config)
    chat, embedding, rerank = _providers(runtime)

    assert dict(chat.backends) == {}
    assert set(embedding.backends) == {ONNXRUNTIME_BACKEND_ID}
    assert dict(rerank.backends) == {}


def test_only_onnx_rerank_configured_wires_only_the_rerank_provider() -> None:
    config = WorkerConfig(
        llamacpp=None,
        vllm=None,
        onnx_embedding=None,
        onnx_rerank=OnnxConfig(model_path="model.onnx", tokenizer_path="tokenizer.json"),
    )

    runtime = build_runtime(config)
    chat, embedding, rerank = _providers(runtime)

    assert dict(chat.backends) == {}
    assert dict(embedding.backends) == {}
    assert set(rerank.backends) == {ONNXRUNTIME_BACKEND_ID}


def test_only_llamacpp_configured_wires_only_the_chat_provider(
    tmp_path: Path, fake_llama_cpp_module: list[object]
) -> None:
    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"stub-gguf")
    config = WorkerConfig(
        llamacpp=LlamaCppConfig(model_path=str(model_path), pool_size=1),
        vllm=None,
        onnx_embedding=None,
        onnx_rerank=None,
    )

    runtime = build_runtime(config)
    chat, embedding, rerank = _providers(runtime)

    assert set(chat.backends) == {LLAMA_CPP_BACKEND_ID}
    assert dict(embedding.backends) == {}
    assert dict(rerank.backends) == {}


def test_engines_are_constructed_exactly_once_per_build_runtime_call_never_per_request(
    tmp_path: Path, fake_llama_cpp_module: list[object]
) -> None:
    # Success criterion / D29: "Backends, and any pooled resources they
    # own (ADR-0003), are constructed once at startup and never per-
    # request, asserted by a construction-count test." llama.cpp is the
    # one engine that eagerly constructs real resources at Backend-
    # construction time (D26/D27), so it is the only one whose
    # construction count is observable without dispatching a real
    # request through a real SDK.
    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"stub-gguf")
    pool_size = 2
    config = WorkerConfig(
        llamacpp=LlamaCppConfig(model_path=str(model_path), pool_size=pool_size),
        vllm=None,
        onnx_embedding=None,
        onnx_rerank=None,
    )

    runtime = build_runtime(config)

    assert len(fake_llama_cpp_module) == pool_size

    chat, _, _ = _providers(runtime)
    backend = chat.backends[LLAMA_CPP_BACKEND_ID]
    plan = ServingPlan(
        model=None,  # type: ignore[arg-type] - acquire()/release() never read `.model`
        backend=LLAMA_CPP_BACKEND_ID,
        quantization=Quantization(scheme="artifact-defined", bits=0),
    )

    async def _simulate_two_requests() -> None:
        session_one = await backend.acquire(plan)
        await backend.release(session_one)
        session_two = await backend.acquire(plan)
        await backend.release(session_two)

    asyncio.run(_simulate_two_requests())

    # Two acquire/release round trips through the pool never construct a
    # third `Llama` instance — the pool built by `build_runtime()` is
    # reused, not rebuilt per request.
    assert len(fake_llama_cpp_module) == pool_size


def test_worker_module_is_the_sole_importer_of_concrete_engine_classes() -> None:
    # `provider-backend-composition` spec: "Composition Root Exclusive
    # Backend Ownership" — only `worker.py` may name a concrete engine
    # class. An `ast`-based scan (not a plain `rg`) so renaming an
    # unrelated symbol that merely contains one of these names as a
    # substring can never produce a false positive.
    #
    # JUDGMENT CALL (flagged, not silently resolved — see apply-progress
    # for Slice 7 / final report): `engines/__init__.py` re-exports all
    # four concrete classes at the package level (frozen, pre-Slice-7
    # convention — see `tests/unit/engines/test_engines_exports.py`,
    # mirroring `tibios_ray.backends`'s own package-exports style). That
    # re-export is a literal `ast.ImportFrom`, so a byte-literal reading
    # of the spec scenario ("only worker.py imports them") is false
    # today, and always was going to be the moment `engines/__init__.py`
    # and a real Composition Root coexist — neither `design.md` nor the
    # spec's own scenario text anticipates the package-level re-export
    # layer. This test resolves the tension the way ADR-0001's own
    # rationale reads (`spec.md`: "No wired Provider MUST construct,
    # look up, or discover a Backend") — `engines/__init__.py` neither
    # constructs anything nor is a Provider; it only aliases a name for
    # ergonomics, so it is exempted by identity, not by directory. Every
    # *other* file in the tree, `engines/` submodules included, is still
    # held to the letter of the rule.
    concrete_engine_class_names = frozenset(
        {
            "LlamaCppTextBackend",
            "VllmTextBackend",
            "OnnxEmbeddingBackend",
            "OnnxRerankBackend",
        }
    )
    _EXEMPT_PACKAGE_REEXPORT = "engines/__init__.py"
    root = Path(tibios_ray.__file__).resolve().parent

    importers: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(
                alias.name in concrete_engine_class_names for alias in node.names
            ):
                importers.add(path.relative_to(root).as_posix())
            elif isinstance(node, ast.Import) and any(
                alias.name.rsplit(".", 1)[-1] in concrete_engine_class_names
                for alias in node.names
            ):
                importers.add(path.relative_to(root).as_posix())

    importers.discard(_EXEMPT_PACKAGE_REEXPORT)

    assert importers == {"worker.py"}, (
        "found a concrete engine class import outside worker.py (and "
        f"outside the documented {_EXEMPT_PACKAGE_REEXPORT} exemption) — "
        f"this breaks Composition Root Exclusive Backend Ownership: {importers}"
    )


def test_end_to_end_wiring_smoke_with_every_engine_configured(
    tmp_path: Path, fake_llama_cpp_module: list[object]
) -> None:
    # Ties slices 1-6 together (not a real-SDK integration test — vLLM/
    # ONNX construction is SDK-free by design, VL2/OR2's lazy init; only
    # llama.cpp needs the fake `sys.modules["llama_cpp"]` above, since
    # D26/D27 made its pool construction eager).
    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"stub-gguf")
    config = WorkerConfig(
        llamacpp=LlamaCppConfig(model_path=str(model_path), pool_size=1),
        vllm=VllmConfig(model="m"),
        onnx_embedding=OnnxConfig(model_path="embed.onnx", tokenizer_path="embed-tok.json"),
        onnx_rerank=OnnxConfig(model_path="rerank.onnx", tokenizer_path="rerank-tok.json"),
    )

    runtime = build_runtime(config)
    chat, embedding, rerank = _providers(runtime)

    assert isinstance(runtime, WorkerRuntime)
    assert set(chat.backends) == {LLAMA_CPP_BACKEND_ID, VLLM_BACKEND_ID}
    assert set(embedding.backends) == {ONNXRUNTIME_BACKEND_ID}
    assert set(rerank.backends) == {ONNXRUNTIME_BACKEND_ID}
