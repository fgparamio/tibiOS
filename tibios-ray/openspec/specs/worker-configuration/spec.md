# Worker Configuration Specification

## Purpose

`worker-configuration` is the configuration surface that supplies
per-engine artifact paths (and Backend-internal sizing knobs, e.g. pool
size per [ADR-0003](../../../docs/adr/0003-backend-resource-ownership.md))
to `worker.py::build_runtime()` — the Composition Root
([ADR-0001](../../../docs/adr/0001-provider-backend-composition.md)).
Its only consumer is the Composition Root; it decides which concrete
engines get built and, by omission, which capabilities stay unwired.

## Requirements

### Requirement: Process-Supplied Per-Engine Artifact Configuration

The runtime MUST obtain per-engine artifact configuration (e.g. model
file paths) from process configuration supplied by the Composition Root.
Missing or malformed configuration MUST be rejected rather than guessed.
The concrete configuration source — environment variables, a structured
file, or a combination with a defined precedence — is defined by the
implementation design, not by this requirement.

#### Scenario: Reads a configured artifact path

- GIVEN process configuration supplying one engine's artifact path
- WHEN the configuration surface is loaded
- THEN the resulting configuration value equals the supplied content, unmodified beyond type parsing

#### Scenario: Absent configuration is represented as absent, not guessed

- GIVEN one engine's artifact path is not supplied by process configuration
- WHEN the configuration surface is loaded
- THEN that engine is represented as unconfigured — no guessed or hardcoded default path is substituted

### Requirement: Unconfigured Engines Yield Unwired Capabilities, Not Startup Crashes

When an engine's required artifact configuration is absent, the
Composition Root MUST NOT construct that engine and MUST NOT crash the
Worker process; the matching `BackendId` MUST be absent from every
Provider's injected mapping, leaving the capability unwired.

#### Scenario: Worker starts with zero configuration present

- GIVEN no engine artifact environment variables are set
- WHEN `build_runtime()` runs
- THEN it returns a `WorkerRuntime` without raising, and every wired capability's Provider has an empty backend mapping

#### Scenario: A partially configured deployment wires only the configured engines

- GIVEN artifact configuration present for exactly one engine and absent for the others
- WHEN `build_runtime()` runs
- THEN only that engine's `BackendId` appears in its matching Provider's injected mapping; other Providers' mappings omit it

### Requirement: Reject-Don't-Guess Configuration Parsing

When an engine's artifact configuration is present but malformed or
incomplete, the configuration surface MUST fail fast and explicitly at
startup — never silently fall back to a default, partially construct the
engine, or guess a substitute value.

#### Scenario: Malformed configuration fails startup explicitly

- GIVEN an environment variable present but not parseable into the shape an engine's configuration requires
- WHEN the configuration surface is loaded
- THEN loading fails with an explicit, attributable error before `build_runtime()` returns a runtime — it does not silently skip the value or substitute a default

### Requirement: Composition Root Is the Configuration Surface's Sole Consumer

Only `worker.py::build_runtime()` MUST read from the configuration
surface. No Provider, Backend, or engine adapter MUST read the
underlying configuration source (whatever it is) or the configuration
surface directly.

#### Scenario: No Provider or Backend module reads configuration directly

- GIVEN the `capabilities/` and `backends/` module trees
- WHEN searched for direct access to the underlying configuration source or imports from the configuration surface
- THEN none is found — configuration reaches those layers only as already-constructed objects passed through `worker.py`

### Requirement: Backend-Internal Resource Sizing Is Independently Configurable

Backend-internal concurrency/residency sizing (ADR-0003) — e.g.
`LlamaCppTextBackend`'s pool size — MUST be configurable through the same
surface, independently of artifact path configuration.

#### Scenario: Pool size is read from its own configuration value

- GIVEN a configured pool-size value for an engine that uses ADR-0003 pooling
- WHEN that engine is constructed by the Composition Root
- THEN it is built with a pool of exactly the configured size

#### Scenario: Absent pool-size configuration falls back to a documented default

- GIVEN artifact configuration present but no explicit pool-size configuration
- WHEN that engine is constructed
- THEN construction succeeds using a documented default pool size — absence of a sizing knob is not treated as absence of the engine's artifact configuration
