# TibiOS Security Guidelines

Version: 1.1

## Purpose

Security is a design principle, not a feature added later. Every crate, API, and protocol must be designed assuming hostile environments.

## Core Principles

Assume compromise. Assume malformed input. Assume malicious users. Assume hostile networks. Trust nothing. Verify everything.

## Secure by Default

The safest configuration must be the default. Users may opt into less secure behavior; they must never accidentally receive it.

## Least Privilege

Every component receives only the permissions it requires. Avoid unnecessary capabilities. Reduce attack surface.

## Validate Input

All external input is untrusted: network packets, files, configuration, environment variables, command-line arguments, serialized objects. Never trust any boundary.

## Fail Securely

When something unexpected happens: deny access, stop processing, return an explicit error. Never continue in an unknown state.

## Secrets

Never store secrets in source code. Never commit them, log them, or expose them in panic messages or `Debug` implementations. Examples: passwords, tokens, certificates, private keys, session identifiers, encryption keys.

## Logging

Logs must never contain credentials, authentication headers, session cookies, personal data, or encryption material. Logs should support incident investigation, not create incidents.

## Authentication vs Authorization

Authentication proves identity. Authorization grants permissions. Never confuse the two.

> This distinction is load-bearing for `22-networking.md`: Networking performs transport-level authentication (Noise), producing a Verified Identity; Trust performs authorization (`Authorize(identity)?`). A peer can prove its identity perfectly and still be rejected — Networking never decides authorization, Trust never establishes sessions.

Authorization must be explicit — never rely on hidden assumptions. Every privileged operation must verify permissions.

## Cryptography

Never implement cryptographic algorithms. Use well-maintained, audited libraries.

## Randomness

Use cryptographically secure randomness whenever security depends on it. Never use predictable generators for secrets.

## Unsafe

Unsafe code expands the trusted computing base. Every unsafe block requires justification, documentation, review, and tests. Unsafe is a security decision.

## Memory / Integer Safety

Rust already prevents many vulnerabilities — do not bypass those guarantees unnecessarily. Assume integer overflow matters; use checked arithmetic where correctness requires it.

## Serialization

Never deserialize untrusted data blindly. Validate versions, sizes, and limits. Reject malformed payloads.

## Resource Limits

Every resource must have limits: message size, request size, queue length, recursion depth, object count, execution time. Unlimited resources invite denial-of-service attacks.

## Network Security

Assume the network is hostile. Verify every message. Authenticate peers. Encrypt sensitive communication. Never trust source addresses.

## Replay Protection / Timeouts

Sensitive operations should resist replay attacks (identifiers or timestamps where appropriate). Every external operation requires a timeout — never wait forever; timeout values belong in configuration.

## Dependencies / Supply Chain

Every dependency increases risk — before adding one, ask if it's maintained, widely used, solves a real problem, and can be audited. Pin dependency versions, review updates, monitor advisories, remove unused dependencies.

## Error Messages

Errors should help developers, not attackers — never expose internal paths, infrastructure topology, implementation details, or sensitive configuration. Public APIs must validate input; never rely on callers for security.

## Filesystem / Temporary Files

Assume file paths are malicious — normalize paths, reject unexpected traversal, validate permissions. Create temporary files securely, with unpredictable names, and remove them when finished.

## Concurrency

Security bugs include race conditions. Shared mutable state increases attack surface. Ownership improves security.

## Denial of Service

Design for overload: reject excessive requests, bound memory/CPU/queues. Graceful degradation is preferable to failure.

## Testing

Security testing includes malformed input, oversized payloads, invalid authentication, corrupted data, replay attempts, permission failures. Security behavior is tested, not assumed.

## Documentation

Document security assumptions, trust boundaries, and threat models. Future engineers should understand what is protected and why.

## Review Checklist

Before merging ask: is all input validated? Are secrets protected? Are permissions explicit? Are resources bounded? Are dependencies justified? Does unsafe expand risk? Are failure modes secure? Could an attacker misuse this API?

## TibiOS Rules

Every node is considered untrusted until authenticated. Every message is considered hostile until validated. Every plugin is considered untrusted until verified. Every distributed component must tolerate malicious peers.

### Scope of "Tolerate Malicious Peers" for the MVP

This rule distinguishes two levels of "malicious," which must not be conflated:

1. **Network/protocol level** — authentication of peers, validation of every message, never trusting source addresses, bounded resources. This is fully in scope for the MVP: enforced by the whitelist/cryptographic-identity Trust model and libp2p's Noise-encrypted channels (see `22-networking.md`).
2. **Compute-integrity level** — can an *already-authenticated* peer's returned computation result be trusted? This is explicitly **out of scope for the MVP** and documented as a known, deliberate limitation (Paradigm A / Phase 2 in the Red Tibi product design) — no system in the ecosystem, including Petals, solves this in production today.

An authenticated whitelisted node that lies about a result is not detected by the MVP. This is a known gap, not an oversight.

Security is enforced by architecture, not by convention.

## Motto

Trust nothing. Validate everything. Design for compromise.
