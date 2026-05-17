# A ticket carries a severity; its priority is derived

Every ticket on a sized board carries a `severity` — `critical`, `major`, `minor` or `trivial` — and `docs-dev/todo/index.py` derives the order work is picked up in from it, from `blocked_by` and from `effort`.
There is no `priority` key ([todo/README.md § Severity](../../todo/README.md#severity), [§ Work order](../../todo/README.md#work-order)).

**What was missing.**
`effort`, `risk` and `impact` all describe the change: what it costs, what catches a mistake in it, and what a user migrates once it lands.
None says what a user suffers while the ticket stays open, so the boards could say how big a ticket was but not whether it mattered, and sorted by ID.

**Why these rungs.**
They are ordered as `impact`'s are, by how late the user finds out: a configuration that loads and means something else (`critical`) passes every check a user runs, a refusal (`major`) is at least loud.
For a library whose job is turning configuration into values, the silent wrong value is the worst outcome there is.
Each rung is anchored to what the reproduction shows — does the user get an error, is there a workaround — rather than to judgement or frequency, for the reason `effort` is anchored to properties of the repository rather than to hours: most tickets are filed by agents in the middle of other work, and two filers must land on the same rung.

**Why four.**
Mozilla's Bugzilla went from seven severities to four in 2020 — S1 catastrophic, S2 serious, S3 normal (a workaround exists), S4 small — because the finer rungs were used inconsistently.
Three would merge "loud, no workaround" with "loud, with one", which is the line between work that blocks a user and work that slows one; five would need anchors finer than a reproduction shows.

**Why derived, not written.**
Rust's `P-critical`…`P-low` labels, Linear's and Jira's priority fields are set by a triage role, at a triage meeting; this repository has neither, and a filer can observe a severity but cannot know the maintainer's plans.
A written priority also goes stale in silence: it changes when *another* ticket gains a blocker, which is the drift the generated tables exist to prevent.
So `index.py` computes it:

- **Effective severity** is a ticket's own, or the highest among the tickets it blocks, transitively and across boards.
  A refactor matters through what it unblocks, and a question through what waits for its answer, without anyone re-scoring either.
- **The order** reads effective severity, then unblocked before blocked, then effort smallest first, then ID.
  Severity over effort is weighted-shortest-job-first (Reinertsen's *cost of delay divided by duration*, as SAFe's WSJF spells it), in its coarsest form: among equally costly delays, the cheapest job first.

**Left out.**
`risk` says how carefully to do the work, not when.
`impact` weighs a breaking change, which before 1.0 is a release plan rather than a property of the ticket.
A maintainer override would be a written priority again; one can be added if derivation proves wrong in practice, and the cases that prompt it are the evidence for its shape.

Cost: every sized ticket needs one more field, and the tables reorder whenever a severity or a blocker changes, so a diff of a board README is no longer append-only.
