//! `runtime` — the workspace's binary crate and Composition Root, per
//! `02-project-structure.md`'s "Composition Root" section.
//!
//! Concrete implementations are assembled only once, here. The `runtime`
//! crate creates concrete services, injects implementations, and wires the
//! Runtime graph; no other crate performs dependency composition. It is the
//! sole deliberate exception to the workspace's narrow-dependency rule: it
//! may depend on every other crate, and no crate may depend on it.
//!
//! Wiring is deferred to a follow-up change — this is a stub.

fn main() {}
