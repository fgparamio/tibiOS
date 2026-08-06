//! `ContentHash` primitive: identity for immutable Content Objects
//! (`13-object-model.md`). `runtime-primitives` never computes a hash
//! itself — hashing algorithms are domain logic (owned by Storage,
//! `21-runtime-storage-engine.md` / `24-replication.md`); this type only
//! holds and compares an already-computed, algorithm-qualified digest
//! (e.g. `"sha256:af23..."`, per `13-object-model.md`'s Model Reference
//! example).

use serde::{Deserialize, Serialize};

/// An algorithm-qualified content digest. Immutable identity for a Content
/// Object.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ContentHash(String);

impl ContentHash {
    /// Wraps an already-computed, algorithm-qualified digest.
    #[must_use]
    pub fn new(digest: impl Into<String>) -> Self {
        Self(digest.into())
    }

    /// The algorithm-qualified digest string.
    #[must_use]
    pub fn digest(&self) -> &str {
        &self.0
    }

    /// Pure Operation: does `candidate` (an already-computed digest, e.g.
    /// from re-hashing a Physical Replica) match this Content Object's
    /// identity?
    #[must_use]
    pub fn matches(&self, candidate: &str) -> bool {
        self.0 == candidate
    }
}

#[cfg(test)]
mod tests {
    use super::ContentHash;

    #[test]
    fn matches_true_for_equal_digest() {
        let hash = ContentHash::new("sha256:af23");
        assert!(hash.matches("sha256:af23"));
    }

    #[test]
    fn matches_false_for_different_digest() {
        let hash = ContentHash::new("sha256:af23");
        assert!(!hash.matches("sha256:zz99"));
    }
}
