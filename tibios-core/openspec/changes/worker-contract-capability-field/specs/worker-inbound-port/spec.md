# Delta for Worker Inbound Port

## ADDED Requirements

### Requirement: ExecutionContext Carries A Mandatory Worker Capability

`ExecutionContext` MUST carry a `WorkerCapability` value naming which behavior an execution requests (e.g. `chat.generate`). This value MUST be exposed via a public read accessor and MUST NOT be optional, defaultable, or omittable — every path that constructs an `ExecutionContext` (public constructor or public fields) MUST supply one. This closes the gap where `tibios-ray`'s `context.py` already models `capability: str` with no contractual wire source.

#### Scenario: A fake ExecutionContext must supply a capability to construct

- GIVEN a test that constructs an `ExecutionContext` value using only public constructors or fields
- WHEN the construction is attempted without a `WorkerCapability` value
- THEN it does not compile — no default or optional path exists to skip it

#### Scenario: WorkerCapability is readable via a public accessor

- GIVEN a constructed `ExecutionContext` value
- WHEN its capability accessor is called
- THEN it returns the exact `WorkerCapability` value supplied at construction
