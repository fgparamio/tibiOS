//! The Object domain's data family: `ObjectType`, `ObjectLifecycle`,
//! `LogicalObject`, `ContentObject`. No Ports yet — `ObjectStore` and
//! resolution are a future change.
//!
//! Implements `13-object-model.md` and `23-object-store.md`.

use runtime_primitives::{ContentHash, ObjectId, ObjectVersion};

/// The Object categories the Runtime recognizes (`13-object-model.md:102`).
/// Closed for now — a new category is a breaking spec change, same
/// convention as `ExecutionEvent`'s six arms in `runtime-worker`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ObjectType {
    /// A unit of computation the Runtime schedules and executes.
    Workload,
    /// A piece of communication between Objects.
    Message,
    /// A long-lived, addressable unit of behavior.
    Actor,
    /// A long-running process exposing capabilities to other Objects.
    Service,
    /// A reference to a collection of data consumed by Workloads.
    Dataset,
    /// A multi-dimensional array used by AI Workloads.
    Tensor,
    /// A saved point-in-time snapshot of a Workload's state.
    Checkpoint,
    /// A versioned, persisted Runtime configuration value.
    Configuration,
    /// A generic named artifact produced or consumed by the Runtime.
    Artifact,
    /// A reference to an AI model.
    Model,
}

/// The eight lifecycle states a Logical Object moves through
/// (`13-object-model.md:73-96`). Deliberately no `Default` impl, and no
/// `transition`/`can_transition`/`validate` method — legality, ownership,
/// and monotonicity of transitions are open questions deferred to the
/// Ports/behavior change (see this change's spec delta).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ObjectLifecycle {
    /// The Object has just been instantiated.
    Created,
    /// The Object has passed validation.
    Validated,
    /// The Object has been recorded in the Runtime's authoritative state.
    Registered,
    /// The Object is ready for use by consumers.
    Available,
    /// The Object is currently referenced by at least one consumer.
    Referenced,
    /// A Logical Object only: a newer version now exists.
    Updated,
    /// The Object is retained but no longer active.
    Archived,
    /// The Object has been removed.
    Deleted,
}

/// A mutable, named reference: identity (`ObjectId` + `ObjectVersion`) plus
/// the `ContentHash` it currently points to (`13-object-model.md`'s Logical
/// Object). Points at a `ContentHash`, not a resolved `ContentObject` —
/// resolving the hash is Object Store work, out of scope here.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LogicalObject {
    id: ObjectId,
    version: ObjectVersion,
    content_hash: ContentHash,
    kind: ObjectType,
}

impl LogicalObject {
    /// Builds a `LogicalObject` from its identity, version, content
    /// reference, and type.
    #[must_use]
    pub fn new(id: ObjectId, version: ObjectVersion, content_hash: ContentHash, kind: ObjectType) -> Self {
        Self {
            id,
            version,
            content_hash,
            kind,
        }
    }

    /// This Logical Object's identity, independent of its version.
    #[must_use]
    pub fn id(&self) -> ObjectId {
        self.id
    }

    /// This Logical Object's current version.
    #[must_use]
    pub fn version(&self) -> ObjectVersion {
        self.version
    }

    /// The `ContentHash` this version currently points to.
    #[must_use]
    pub fn content_hash(&self) -> &ContentHash {
        &self.content_hash
    }

    /// This Object's category.
    #[must_use]
    pub fn kind(&self) -> ObjectType {
        self.kind
    }
}

/// Immutable content addressed by a `ContentHash` (`13-object-model.md`'s
/// Content Object). MUST NOT reference back to any `LogicalObject` — the
/// reference direction is `LogicalObject -> ContentHash` only, so many
/// (even unrelated) `LogicalObject`s may share one `ContentObject`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ContentObject {
    hash: ContentHash,
}

impl ContentObject {
    /// Wraps an already-identified content hash as a `ContentObject`.
    #[must_use]
    pub fn new(hash: ContentHash) -> Self {
        Self { hash }
    }

    /// This Content Object's immutable identity.
    #[must_use]
    pub fn hash(&self) -> &ContentHash {
        &self.hash
    }
}

#[cfg(test)]
mod tests {
    use super::{ContentObject, LogicalObject, ObjectLifecycle, ObjectType};
    use runtime_primitives::{ContentHash, ObjectId, ObjectVersion};

    #[test]
    fn logical_object_round_trips_its_fields() {
        let id = ObjectId::new();
        let version = ObjectVersion::initial();
        let content_hash = ContentHash::new("sha256:af23");
        let obj = LogicalObject::new(id, version, content_hash.clone(), ObjectType::Model);

        assert_eq!(obj.id(), id);
        assert_eq!(obj.version(), version);
        assert_eq!(obj.content_hash(), &content_hash);
        assert_eq!(obj.kind(), ObjectType::Model);
    }

    #[test]
    fn logical_object_implements_clone() {
        let obj = LogicalObject::new(
            ObjectId::new(),
            ObjectVersion::initial(),
            ContentHash::new("sha256:af23"),
            ObjectType::Dataset,
        );
        let cloned = obj.clone();
        assert_eq!(obj, cloned);
    }

    #[test]
    fn content_object_round_trips_its_hash() {
        let hash = ContentHash::new("sha256:af23");
        let content = ContentObject::new(hash.clone());
        assert_eq!(content.hash(), &hash);
    }

    #[test]
    fn content_object_implements_clone() {
        let content = ContentObject::new(ContentHash::new("sha256:af23"));
        let cloned = content.clone();
        assert_eq!(content, cloned);
    }

    #[test]
    fn two_distinct_logical_objects_may_share_one_content_object() {
        let shared_hash = ContentHash::new("sha256:af23");
        let a = LogicalObject::new(
            ObjectId::new(),
            ObjectVersion::initial(),
            shared_hash.clone(),
            ObjectType::Model,
        );
        let b = LogicalObject::new(
            ObjectId::new(),
            ObjectVersion::initial(),
            shared_hash.clone(),
            ObjectType::Model,
        );
        assert_ne!(a.id(), b.id());
        assert_eq!(a.content_hash(), b.content_hash());
    }

    #[test]
    fn object_lifecycle_has_eight_variants_matching_the_doc() {
        let variants = [
            ObjectLifecycle::Created,
            ObjectLifecycle::Validated,
            ObjectLifecycle::Registered,
            ObjectLifecycle::Available,
            ObjectLifecycle::Referenced,
            ObjectLifecycle::Updated,
            ObjectLifecycle::Archived,
            ObjectLifecycle::Deleted,
        ];
        assert_eq!(variants.len(), 8);
    }

    // ObjectLifecycle::default() intentionally has no runtime test: Rust
    // has no stable way to assert trait *absence* in a passing test.
    // Verified by review instead (task 5.3) — no `impl Default for
    // ObjectLifecycle` exists in this file.

    #[test]
    fn object_type_has_ten_variants_matching_the_doc() {
        let variants = [
            ObjectType::Workload,
            ObjectType::Message,
            ObjectType::Actor,
            ObjectType::Service,
            ObjectType::Dataset,
            ObjectType::Tensor,
            ObjectType::Checkpoint,
            ObjectType::Configuration,
            ObjectType::Artifact,
            ObjectType::Model,
        ];
        assert_eq!(variants.len(), 10);
    }
}
