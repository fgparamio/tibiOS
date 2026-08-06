//! `ExecutionContext` and the values it carries: the immutable input a
//! Worker receives to perform one execution (`18-worker-model.md:52`).
//! Constructing one requires no async runtime, no transport, and no
//! private adapter module — the Worker Inbound Port's own testability
//! claim (`worker-inbound-port` capability).

use std::collections::BTreeMap;

use runtime_allocation::AllocationContract;
use runtime_primitives::{AllocationId, ContentHash, ObjectId, ObjectVersion, WorkloadId};

/// A single already-resolved dependency reference carried inside an
/// `ExecutionContext`, mirroring the wire's `ResolvedModelRef`
/// field-for-field (`18-worker-model.md:52`). This change's proposal
/// Decision #1: a resolved reference is not an `Object` — the Worker
/// receives already-resolved coordinates and never rediscovers or
/// re-resolves them itself.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResolvedDependency {
    object_id: ObjectId,
    object_version: ObjectVersion,
    content_hash: ContentHash,
}

impl ResolvedDependency {
    /// Builds a `ResolvedDependency` from its three already-resolved
    /// coordinates.
    #[must_use]
    pub fn new(
        object_id: ObjectId,
        object_version: ObjectVersion,
        content_hash: ContentHash,
    ) -> Self {
        Self {
            object_id,
            object_version,
            content_hash,
        }
    }

    /// The identity of the referenced Logical Object, independent of its
    /// version.
    #[must_use]
    pub const fn object_id(&self) -> ObjectId {
        self.object_id
    }

    /// The specific version of the referenced Logical Object that was
    /// resolved.
    #[must_use]
    pub const fn object_version(&self) -> ObjectVersion {
        self.object_version
    }

    /// The content digest the resolved reference was pinned to.
    #[must_use]
    pub const fn content_hash(&self) -> &ContentHash {
        &self.content_hash
    }
}

/// The execution-scoped authorization envelope this one execution runs
/// under. Supplied by the Runtime, never negotiated and never derived
/// (`proto-worker-contract/design.md` D1). Every field is **carried, never
/// interpreted**: the Worker attaches them to observability and to the
/// Execution Report's provenance, and makes no decision from them
/// (`18-worker-model.md:136`, `20-admission-control.md:47` — that
/// authority belongs to Admission, not to the Worker). `runtime-security`
/// is the future owner of this whole envelope; when it re-types these
/// fields it does so as one unit, not field-by-field (design.md D10
/// Consequences).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SecurityContext {
    tenant_id: String,
    principal_id: String,
    grant_scope: Vec<String>,
}

impl SecurityContext {
    /// Builds a `SecurityContext` from its three carried, uninterpreted
    /// values.
    #[must_use]
    pub fn new(
        tenant_id: impl Into<String>,
        principal_id: impl Into<String>,
        grant_scope: Vec<String>,
    ) -> Self {
        Self {
            tenant_id: tenant_id.into(),
            principal_id: principal_id.into(),
            grant_scope,
        }
    }

    /// The carried tenant identifier, verbatim. Never parsed, never
    /// validated, never branched on inside the Worker.
    #[must_use]
    pub fn tenant_id(&self) -> &str {
        &self.tenant_id
    }

    /// The carried principal identifier, verbatim.
    #[must_use]
    pub fn principal_id(&self) -> &str {
        &self.principal_id
    }

    /// The carried grant scope, verbatim.
    #[must_use]
    pub fn grant_scope(&self) -> &[String] {
        &self.grant_scope
    }
}

/// Tracing identifiers attached to one execution (`09-observability.md:47`).
/// If the message's own identifiers disagree with anything derived from the
/// transport, the message wins.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ObservabilityContext {
    trace_id: String,
    span_id: String,
}

impl ObservabilityContext {
    /// Builds an `ObservabilityContext` from its two carried identifiers.
    #[must_use]
    pub fn new(trace_id: impl Into<String>, span_id: impl Into<String>) -> Self {
        Self {
            trace_id: trace_id.into(),
            span_id: span_id.into(),
        }
    }

    /// The carried trace identifier.
    #[must_use]
    pub fn trace_id(&self) -> &str {
        &self.trace_id
    }

    /// The carried span identifier.
    #[must_use]
    pub fn span_id(&self) -> &str {
        &self.span_id
    }
}

/// The immutable input a Worker receives to perform one execution
/// (`18-worker-model.md:52`). Deliberately excludes the Execution Channel
/// and any cancellation signal — both arrive as separate Inbound Port
/// parameters, never as fields of this value (`worker.proto:68`,
/// `worker-inbound-port` capability). `execution_parameters` is a
/// `BTreeMap`, not a `HashMap`, so execution stays deterministic
/// (`18-worker-model.md:13`) and equality is reproducible in tests.
#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionContext {
    workload_id: WorkloadId,
    allocation_id: AllocationId,
    allocation_contract: AllocationContract,
    dependencies: Vec<ResolvedDependency>,
    security_context: SecurityContext,
    observability_context: ObservabilityContext,
    execution_parameters: BTreeMap<String, String>,
}

impl ExecutionContext {
    /// Builds an `ExecutionContext` from plain values — no async runtime,
    /// no transport, and no private adapter module required.
    #[must_use]
    pub fn new(
        workload_id: WorkloadId,
        allocation_id: AllocationId,
        allocation_contract: AllocationContract,
        dependencies: Vec<ResolvedDependency>,
        security_context: SecurityContext,
        observability_context: ObservabilityContext,
        execution_parameters: BTreeMap<String, String>,
    ) -> Self {
        Self {
            workload_id,
            allocation_id,
            allocation_contract,
            dependencies,
            security_context,
            observability_context,
            execution_parameters,
        }
    }

    /// The identity of the Workload this execution belongs to — the
    /// correlation key a `WorkerService` implementation registers before
    /// its first suspension point.
    #[must_use]
    pub const fn workload_id(&self) -> WorkloadId {
        self.workload_id
    }

    /// The carried tracing identifiers for this execution — additive,
    /// read-only access so a `WorkerService` implementation can attach them
    /// to the `ExecutionReport` it owes (`worker-composition-root/design.md`
    /// D4). Zero new dependencies, zero behavior change: this is an
    /// approved deviation from this change's own proposal, not a
    /// reinterpretation of the field.
    #[must_use]
    pub const fn observability_context(&self) -> &ObservabilityContext {
        &self.observability_context
    }

    /// The execution-scoped allocation contract carried by this context —
    /// additive, read-only access (`worker-composition-root/design.md` D4).
    /// `AllocationContract` is `Copy`, so this returns by value, mirroring
    /// `workload_id`'s own accessor shape.
    #[must_use]
    pub const fn allocation_contract(&self) -> AllocationContract {
        self.allocation_contract
    }

    /// The carried, opaque execution parameters — additive, read-only
    /// access (`worker-composition-root/design.md` D4). Never interpreted
    /// by this accessor; a `WorkerService` implementation decides what, if
    /// anything, each key means.
    #[must_use]
    pub const fn execution_parameters(&self) -> &BTreeMap<String, String> {
        &self.execution_parameters
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use runtime_allocation::AllocationContract;
    use runtime_primitives::{AllocationId, ContentHash, ObjectId, ObjectVersion, WorkloadId};

    use super::{ExecutionContext, ObservabilityContext, ResolvedDependency, SecurityContext};

    fn sample_context(workload_id: WorkloadId) -> ExecutionContext {
        let dependency = ResolvedDependency::new(
            ObjectId::new(),
            ObjectVersion::initial(),
            ContentHash::new("sha256:af23"),
        );
        let mut execution_parameters = BTreeMap::new();
        execution_parameters.insert("temperature".to_string(), "0.7".to_string());

        ExecutionContext::new(
            workload_id,
            AllocationId::new(),
            AllocationContract::new(core::time::Duration::from_secs(30)),
            vec![dependency],
            SecurityContext::new("tenant-1", "principal-1", vec!["scope-a".to_string()]),
            ObservabilityContext::new("trace-1", "span-1"),
            execution_parameters,
        )
    }

    #[test]
    fn execution_context_constructs_from_plain_values_and_exposes_its_workload_id() {
        let workload_id = WorkloadId::new();
        let context = sample_context(workload_id);
        assert_eq!(context.workload_id(), workload_id);
    }

    #[test]
    fn execution_context_clone_round_trips_to_an_equal_value() {
        let original = sample_context(WorkloadId::new());
        let cloned = original.clone();
        assert_eq!(original, cloned);
    }

    #[test]
    fn execution_context_observability_context_accessor_returns_the_carried_value_verbatim() {
        let context = sample_context(WorkloadId::new());

        assert_eq!(context.observability_context().trace_id(), "trace-1");
        assert_eq!(context.observability_context().span_id(), "span-1");
    }

    #[test]
    fn execution_context_allocation_contract_accessor_returns_the_carried_value_verbatim() {
        let context = sample_context(WorkloadId::new());

        assert_eq!(
            context.allocation_contract(),
            AllocationContract::new(core::time::Duration::from_secs(30))
        );
    }

    #[test]
    fn execution_context_execution_parameters_accessor_returns_the_carried_map_verbatim() {
        let context = sample_context(WorkloadId::new());

        assert_eq!(
            context.execution_parameters().get("temperature"),
            Some(&"0.7".to_string())
        );
    }

    #[test]
    fn security_context_accessors_return_the_carried_strings_verbatim() {
        let security_context = SecurityContext::new(
            "tenant-1",
            "principal-1",
            vec!["scope-a".to_string(), "scope-b".to_string()],
        );

        assert_eq!(security_context.tenant_id(), "tenant-1");
        assert_eq!(security_context.principal_id(), "principal-1");
        assert_eq!(
            security_context.grant_scope(),
            &["scope-a".to_string(), "scope-b".to_string()]
        );
    }

    #[test]
    fn observability_context_accessors_return_the_carried_strings_verbatim() {
        let observability_context = ObservabilityContext::new("trace-1", "span-1");

        assert_eq!(observability_context.trace_id(), "trace-1");
        assert_eq!(observability_context.span_id(), "span-1");
    }

    #[test]
    fn resolved_dependency_accessors_return_the_carried_coordinates() {
        let object_id = ObjectId::new();
        let object_version = ObjectVersion::initial();
        let content_hash = ContentHash::new("sha256:af23");
        let dependency = ResolvedDependency::new(object_id, object_version, content_hash.clone());

        assert_eq!(dependency.object_id(), object_id);
        assert_eq!(dependency.object_version(), object_version);
        assert_eq!(dependency.content_hash(), &content_hash);
    }
}
