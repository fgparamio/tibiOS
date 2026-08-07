# Architecture Decision Records

An ADR captures a single architecturally significant decision: the context
that forced it, the decision itself, and its consequences — the *why* behind
the system's shape, not the *what*. Format follows Michael Nygard's
[original proposal](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

## When to write one

Write an ADR when a decision is permanent-ish and would be expensive to
reconstruct the reasoning for later — e.g. composition root shape, capability
routing, engine/registry lifecycle, scheduler heuristics, memory management.

Don't write one for a decision that's really a feature change (new
capability, new backend, new endpoint) — that belongs in `openspec/` instead.
Rule of thumb: OpenSpec documents *what* changed; an ADR documents *why the
architecture is shaped this way*.

## Format

One page. Sections:

- **Status** — `Proposed`, `Accepted`, `Superseded by 000X`, or `Deprecated`.
- **Context** — the forces at play (technical, project, constraints) that make
  this decision necessary. Stated neutrally, not as an argument for the
  decision.
- **Decision** — the change being proposed, stated as a firm response
  ("we will..."), not a discussion of alternatives.
- **Consequences** — the resulting context after applying the decision, both
  positive and negative. Include what becomes harder, not just what becomes
  easier.

## Numbering

Sequential, zero-padded to 4 digits, never reused: `0001-`, `0002-`, ...
A superseding ADR gets its own new number; the old one's Status changes to
`Superseded by 000X`, its content stays as a historical record.
