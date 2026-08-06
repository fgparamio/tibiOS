//! The Worker domain's execution-scoped types (`18-worker-model.md`): the
//! immutable input a Worker receives to perform one execution, and — added
//! alongside this module by a sibling slice of this same change — the
//! events a Worker emits and the reports it returns while performing it.

pub mod context;
