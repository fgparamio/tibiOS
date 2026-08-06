# Capability Registry Specification

## Purpose

The Capability Registry defines the Capability Provider interface and lets Capability Providers register and advertise their capability/catalog (model families, backends, flags such as streaming/tools/json/reasoning) so the Worker Runtime can dispatch without hardcoding providers or models.

## Requirements

### Requirement: Capability Provider Interface

The Capability Registry MUST define a Capability Provider protocol/ABC that every Capability Provider implements, exposing its declared capability (e.g. `chat.generate`) and a catalog of supported model families, backends, and capability flags (streaming, tools, json, reasoning).

#### Scenario: A conforming Capability Provider registers successfully

- GIVEN a class implementing the Capability Provider protocol with a non-empty catalog
- WHEN it registers with the Capability Registry
- THEN the registry accepts it and stores its capability + catalog

#### Scenario: A Capability Provider without a catalog is rejected

- GIVEN a class implementing the Capability Provider protocol but declaring no catalog
- WHEN it attempts to register
- THEN the Capability Registry rejects the registration

### Requirement: Aggregated Capability Advertisement

The Capability Registry MUST expose an aggregated, read-only view of all registered Capability Providers' capabilities and catalogs to the Worker Runtime, without hardcoding any specific provider, model, or vendor.

#### Scenario: Worker Runtime queries the aggregated catalog

- GIVEN two or more registered Capability Providers
- WHEN the Worker Runtime queries the Capability Registry for available capabilities
- THEN it receives the union of all registered providers' catalogs, sourced from no hardcoded list

### Requirement: No Local-Infer vs tibios-ray Routing Logic

The Capability Registry and every component in this capability MUST NOT encode any rule that chooses between `local-infer` and tibios-ray, or that routes by model size/cost, per `25-ai-runtime.md` Anti-Patterns.

#### Scenario: Registry code contains no routing rule

- GIVEN the Capability Registry implementation
- WHEN reviewed for conditionals comparing model size/cost or referencing `local-infer`
- THEN none are found
