# Diagram: Runtime API / SDK / CLI

Source: `26-runtime-api.md`, `27-sdk.md`, `28-cli.md`.

```mermaid
flowchart TB
    RuntimeAPI["Runtime API Surface (26)"]
    SDK["SDK (27) — projection pattern, multi-language"]
    CLI["CLI (28) — projection pattern, multi-implementation"]
    Other["Other Clients (e.g. another TibiOS Runtime, 31-federation.md)"]

    RuntimeAPI --> SDK
    RuntimeAPI --> CLI
    RuntimeAPI --> Other

    Domains["Runtime Domains (13-25)"] --> RuntimeAPI
```

Notes: a star graph, not a chain. Every consumer depends only on the Runtime API; no consumer depends on another (`Runtime API → SDK → CLI` was explicitly rejected as an unnecessarily strong dependency). Domains own meaning; `runtime-api` is the sole owner of the public surface.
