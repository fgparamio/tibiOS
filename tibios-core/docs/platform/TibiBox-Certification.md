# TibiBox Platform Certification

Status: Draft (not part of Architecture v1.0's frozen normative set — see
`../architecture/README.md`). This document tracks product/deployment
facts, not Runtime architecture: it changes as hardware validation
happens, without opening an Architecture v1.1.

## What this document is

`25-ai-runtime.md` already establishes the rule this document lives
under: *"The Runtime distinguishes only capabilities, never
implementations."* Nothing here changes that. This document does not
say "TibiOS requires Engine X" — it says which Engine **implementations**
are certified, per Worker, per hardware platform, for the TibiBox product.

Certification is earned by validation on real hardware, not assumed from
a wheel existing on PyPI or a vendor claiming support.

## Reference Platforms

| Platform | Role |
|----------|------|
| x86_64 + CUDA | Dev/CI reference platform. Where Engines are built and unit-tested today. |
| NVIDIA Jetson Orin (JetPack) | First physical TibiBox hardware. Enclosure is being 3D-printed now (as of 2026-08-07); board bring-up has not started yet. |

## Official Engine Catalog (v1.0)

Fixed by the user 2026-08-06. Split by Worker, because "official
implementations" is a product decision, not a Runtime/Worker-contract
limitation — `local-infer` and `tibios-ray` both implement the same
Worker contract (`18-worker-model.md`) and could in principle host any
Engine; this table records which ones actually will.

| Engine | Edge (TibiBox / `local-infer`) | Distributed (`tibios-ray`) |
|--------|:---:|:---:|
| llama.cpp | ✅ | ✅ |
| TensorRT-LLM | ✅ (Jetson-native) | ✅ |
| ONNX Runtime | ✅ | ✅ |
| Faster-Whisper | ✅ | ✅ |
| Kokoro | ✅ | ✅ |
| vLLM | — | ✅ (flagship distributed engine) |

## Engine Priority

Certification is not priority. Every Engine in the catalog above is officially
supported by both Workers, but each Worker has one preferred primary Engine
per text-generation Capability plus a deliberate secondary — decided by the
user 2026-08-07.

| Worker | Priority | Engine |
|--------|----------|--------|
| `local-infer` | Primary | TensorRT-LLM — Jetson-native, the strategic engine for TibiBox/Orin |
| `local-infer` | Secondary | llama.cpp — universal compatibility |
| `tibios-ray` | Primary | vLLM — flagship distributed engine |
| `tibios-ray` | Secondary | llama.cpp — fallback and the GGUF ecosystem |
| both | Sole engine, no secondary | ONNX Runtime (Embeddings, Reranking), Faster-Whisper (STT), Kokoro (TTS) — no NVIDIA dependency, nothing to prioritize |

**Why llama.cpp keeps official certification, not dev-tool-only status**
(decided by the user, 2026-08-07): it remains the de facto standard for GGUF
models; it runs on macOS, Linux, and Windows; it runs most open-source models
without depending on TensorRT; it is the natural fit for development, CI, and
non-NVIDIA hardware; and it keeps TibiOS portable. TensorRT-LLM and vLLM stay
the preferred Engines wherever the actual deployment target is a TibiBox/Orin
or a CUDA-distributed cluster — llama.cpp is not a downgrade path, it is the
compatibility layer that keeps the platform from being NVIDIA-exclusive.
`DeepSeek` and `Kimi` are model families, not Engines, and never appear as a
row in the Engine Catalog above.

## Certification Status

| Engine | Worker | x86_64 | Jetson Orin | Status |
|--------|--------|:---:|:---:|--------|
| llama.cpp | `tibios-ray` | ✅ | 🔶 assumed | Implemented (`llamacpp-backend`, archived 2026-08-06). Jetson not yet hardware-validated, but llama.cpp's own ARM64/CUDA build story is mature — low risk. |
| llama.cpp | `local-infer` | 🔶 assumed | 🔶 assumed | Implemented (`local-infer-llamacpp-engine`, 2026-08-07). CPU-only by design (`local-infer-llamacpp-engine/spec.md`) — no GPU/Metal/CUDA/ROCm path. Model-free Tier 1/2 tests (build, link, and clean-rejection paths) are green everywhere CI runs; the one Tier-3 end-to-end decode test (`-- --ignored`) requires an operator-supplied GGUF model and has not yet run on x86_64 or Jetson Orin hardware — blocked on operator model/hardware access, not on implementation. |
| vLLM | `tibios-ray` | ✅ | 🔶 assumed | Implemented (`vllm-backend`, archived 2026-08-07). **Known risk**: the standard PyPI wheel path (what `pyproject.toml`'s `vllm` extra uses today) is reported unreliable on Jetson by NVIDIA forum users and the community; the working path there is NVIDIA/community Docker containers (`nvidia-ai-iot/vllm`, `dustynv/vllm`), not `pip`/`uv`. See "Open Questions" below — this needs resolving before Jetson certification, not just testing. |
| TensorRT-LLM | `local-infer`, `tibios-ray` | — | — | Not yet implemented in either Worker. NVIDIA's own first-party engine for Jetson — likely the lowest-friction path once built, ahead of vLLM for the Edge/TibiBox column specifically. |
| ONNX Runtime | `local-infer`, `tibios-ray` | — | — | Not yet implemented. |
| Faster-Whisper | `local-infer`, `tibios-ray` | — | — | Not yet implemented. Needs its own Backend Adapter contract (speech, not `TextGenerationBackend`). |
| Kokoro | `local-infer`, `tibios-ray` | — | — | Not yet implemented. Same adapter-contract note as Faster-Whisper. |

Legend: ✅ certified · 🔶 assumed / not hardware-validated yet · — not applicable or not yet built.

## Certification Process

**Phase 1 — POC / first TibiBox units.** An Engine ships as *Experimental*
if it passes the x86_64 dev gate (unit tests, `ruff`, `pyright`/equivalent)
but has no Jetson Orin validation yet. This is enough to demonstrate the
distributed-TibiOS concept; it is not enough to certify.

**Phase 2 — after Orin hardware arrives.** An Engine moves from
*Experimental* to *Certified* for Jetson Orin only after, on real
hardware:

1. Clean install from a documented, repeatable procedure.
2. VRAM consumption measured.
3. Latency measured.
4. Throughput measured.
5. Multi-hour stability run with no leak/crash.

No Engine skips this to become "the default" — certification is earned
per Engine, per platform, independent of how flagship it is on x86_64.

## Decided: Which Worker Runs on the First Physical Orin Unit

`tibios-ray`, until `local-infer` has a TensorRT-LLM adapter (decided by
the user, 2026-08-07). The Engine Catalog's Edge/TibiBox column
(`local-infer` + Jetson-native TensorRT-LLM) is the longer-term target,
but `tibios-ray` is what's actually built today (`llamacpp-backend`,
`vllm-backend`, both archived) — so it runs first, as an interim step,
not a change to the Catalog itself.

**Consequence**: the vLLM PyPI-wheel-on-Jetson risk (Certification
Status table above) is no longer a deferred concern — it is now the
first thing to validate once the Orin board arrives, ahead of any other
item in this document. `pyproject.toml`'s `vllm` extra (`uv`/PyPI
install) should be treated as unverified for Jetson until Phase 2
certification actually runs; do not assume it will install cleanly
there. TensorRT-LLM certification remains blocked on a `local-infer`
adapter that does not exist yet, and stays the eventual target for the
Edge/TibiBox column once built.
