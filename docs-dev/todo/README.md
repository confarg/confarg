# Boards

Open work on confarg, split into four boards. They are the standing place for
**drive-by findings**: anything you notice while doing something else and must not
silently fix, forget, or fold into an unrelated change.

| Board | Holds |
|---|---|
| [bugs.md](bugs.md) | Things that are wrong: defects, parity gaps, code that deviates from the documented intent. |
| [features.md](features.md) | Things that are missing: desirable behavior, and unvetted ideas worth considering. |
| [refactors.md](refactors.md) | Things that work but should be cleaner: duplication, misplaced code, dead weight, test hygiene, performance. |
| [questions.md](questions.md) | Things only the maintainer can settle: missing rationale, undecided trade-offs. |

The boards say *what is left to do*. `../architecture/` says *why the code is the way
it is*. A closed ticket often leaves a decision behind — the decision goes to
`../architecture/`, not here.

## Filing a ticket

Found something outside the scope of what you were asked to do? File it here and carry
on with the task; do not widen the change. One finding, one ticket.

```markdown
### BUG-7 — One-line summary in the imperative or as a defect statement

**Where:** `src/confarg/_parse_env.py` · **Filed:** 2026-09-12 · *(inferred — from code
reading, no test covers it)*
**Effort:** M · **Risk:** high

Two or three lines: what is wrong, when it bites, and what the fix direction looks like.
Link the rationale it touches: [07-expressions.md#deferral-rule](../architecture/07-expressions.md#deferral-rule).
```

- **ID**: prefix (`BUG` / `FEAT` / `REF` / `Q`) plus the next unused number on that board.
  IDs are never reused, so they stay greppable in code comments and revision descriptions.
- **Confidence**: mark anything you have not actually observed as *(inferred)*, as in the
  architecture notes. A suspicion is worth filing; a suspicion sold as a fact is not.
- **Effort and risk**: every ticket on `bugs.md`, `features.md` and `refactors.md` carries
  both, on their own line under `**Where:**`. See [Effort and risk](#effort-and-risk).
  `questions.md` is exempt — a question is answered, not implemented.
- **Ordering**: newest at the bottom of its section. There is no priority field — say it in
  the body if it matters.
- Keep it short. The code and `../architecture/` hold the detail; a ticket only has to be
  enough to pick the work up cold.

## Effort and risk

Two independent axes, so a ticket can be picked up cold without reading the code first. They
really are independent: BUG-4 is a small, well-understood edit to the coercion core that can
break every channel (`S`, high), while REF-8 is a wide mechanical sweep of the test suite that
can break nothing (`M`, low). Estimate both from the ticket body and the source it names.

**Effort** — how much work the change is, anchored to properties of this repository rather
than to hours, which nobody can predict and which age badly:

| | |
|---|---|
| `S` | One module, mechanical. The design is obvious and the existing tests already cover the behavior. |
| `M` | A few modules, or one channel or front-end. The design is settled; the work is writing it and its tests. |
| `L` | Crosses channels or front-ends, **or** needs a new decision recorded in `../architecture/`, **or** sweeps the whole test suite. |
| `XL` | A new subsystem or a new public seam, with several design axes still open. |

**Risk** — the blast radius *if the change turns out to be wrong*, not how likely that is.
Uncertainty about the approach is already visible in the effort size and in the *(inferred)*
marker; this axis answers "how much breaks, and how quietly":

| | |
|---|---|
| `low` | Isolated, or test-only. A mistake surfaces as a failing test. |
| `medium` | One channel or front-end, or a public error message. A mistake can misbehave silently there while the other channels stay correct. |
| `high` | The merge core, the coercion rules, the expression engine, or anything in [09-invariants.md](../architecture/09-invariants.md) — the [fragile couplings](../architecture/09-invariants.md#fragile-couplings) above all. A mistake can break every channel and every front-end at once, which is exactly what [cross-channel parity](../architecture/09-invariants.md#cross-channel-parity) forbids. |

An unvetted idea has no design yet, so its implementation cannot honestly be sized. Size the
**design pass** instead — deciding whether to do it at all is the next actionable step — and
say so: `**Effort:** M *(design pass; implementation not sized)*`. Size that pass by the
investigation it needs, not by the `L` clause above: a design pass always ends in a decision
record, so reading that clause literally would make every one of them `L`. Risk stays the
blast radius of the eventual change; that much is knowable from where the code would have to
go, even before the design exists.

## Closing a ticket

Delete the entry, mention its ID in the `jj describe` message, and record any lasting
decision in `../architecture/`, as the project instructions require. Deciding *not* to do
something also closes a ticket — record that refusal and its reason in
`../architecture/10-design-decisions.md` before deleting, or the ticket will be filed again
in six months.
