# Delta for Worker Wire Adapter

## ADDED Requirements

### Requirement: Domain ExecutionContext And Wire CancelAck Complete The Round-Trip Boundary

`convert.rs` MUST provide `From<runtime_worker::ExecutionContext> for proto::ExecutionContext` (domain→wire, infallible, needed to build a `SubmitJob` request) and `From<proto::CancelAck> for runtime_worker::CancelAck` (wire→domain, infallible — the wire message is empty and the domain type is a unit struct). Neither conversion introduces a new rejection case; both stay outside the `TryFrom`/`Classify` machinery this boundary otherwise requires.

#### Scenario: Domain ExecutionContext converts to its wire message

- GIVEN a `runtime_worker::ExecutionContext` domain value
- WHEN it is converted via `From` into `proto::ExecutionContext`
- THEN every field it carries (including `worker_capability`) is present and correctly populated on the wire message

#### Scenario: Wire CancelAck converts to the domain unit struct

- GIVEN a wire `proto::CancelAck` message
- WHEN it is converted via `From` into `runtime_worker::CancelAck`
- THEN the conversion always succeeds, producing the domain unit struct
