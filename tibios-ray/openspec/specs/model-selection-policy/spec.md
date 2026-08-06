# Model Selection Policy Specification

## Purpose

Given an already-resolved concrete Model ObjectId, the Model Selection Policy decides HOW to serve it: which backend and which quantization/precision. It MUST be structurally incapable of accepting a raw family string and picking a model itself — that is scheduling-time discovery, forbidden for Workers per `18-worker-model.md` ("Dependency References already resolved").

## Requirements

### Requirement: Input Is Restricted to a Resolved Model ObjectId

The Model Selection Policy's entry point MUST accept only an already-resolved concrete Model ObjectId. Its signature MUST NOT offer any parameter, overload, or code path that accepts a raw model-family string (e.g. `"deepseek"`) as a substitute for a resolved ObjectId.

#### Scenario: Policy invoked with a resolved ObjectId returns a serving decision

- GIVEN a concrete, resolved Model ObjectId
- WHEN the Model Selection Policy is invoked
- THEN it returns a decision containing exactly a backend choice and a quantization/precision choice

#### Scenario: Passing a bare family string is structurally impossible

- GIVEN the Model Selection Policy's public entry point signature
- WHEN inspected (type signature and/or attempted call with a bare `str` family name)
- THEN no accepted parameter type or overload permits a bare family string; the call fails type-checking or is rejected at the interface boundary

### Requirement: Decision Scope Excludes Model Discovery

The Model Selection Policy MUST limit its output to backend and quantization/precision selection. It MUST NOT perform family-to-model resolution, catalog search, or any other form of model discovery.

#### Scenario: Decision output contains no discovery step

- GIVEN a resolved Model ObjectId as input
- WHEN the Model Selection Policy produces its decision
- THEN the decision references only backend and quantization/precision — no alternate model, family match, or catalog lookup is performed or returned
