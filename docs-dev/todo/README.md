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
Boards hold open work only: an entry is deleted when it closes, and its ID is named in the
revision that closed it.

## Ticket format

````markdown
### BUG-7 — One-line summary in the imperative or as a defect statement

**Where:** `src/confarg/_parse_env.py` · **Filed:** 2026-09-12 · *(inferred — from code
reading, no test covers it)*
**Effort:** M · **Risk:** high

Two or three lines: what is wrong, when it bites, and what the fix direction looks like.
Link the rationale it touches: [07-expressions.md#deferral-rule](../architecture/07-expressions.md#deferral-rule).

```python
@dataclass
class Config:
    port: int = 8080

confarg.load(Config, argv=[], env={"MYAPP_PORT": "5432"}, env_prefix="MYAPP_")
# expected: Config(port=5432)
# actual:   Config(port=8080)
```
````

- **ID**: prefix (`BUG` / `FEAT` / `REF` / `Q`) plus the next unused number on that board.
  IDs are never reused, so they stay greppable in code comments and revision descriptions.
- **Confidence**: mark anything you have not actually observed as *(inferred)*, as in the
  architecture notes. A suspicion is worth filing; a suspicion sold as a fact is not.
- **Reproduction**: every ticket on `bugs.md` ends with a runnable snippet contrasting the
  expected outcome with the actual one. See [Reproduction](#reproduction). The other three
  boards are exempt — nothing is broken yet to reproduce.
- **Effort and risk**: every ticket on `bugs.md`, `features.md` and `refactors.md` carries
  both, on their own line under `**Where:**`. See [Effort and risk](#effort-and-risk).
  `questions.md` is exempt — a question is answered, not implemented.
- **Ordering**: newest at the bottom of its section. There is no priority field — say it in
  the body if it matters.
- Keep it short. The code and `../architecture/` hold the detail; a ticket only has to be
  enough to pick the work up cold.

## Reproduction

A bug ticket is not filed until someone else can see the bug for themselves. Every entry on
`bugs.md` therefore ends with a **reproduction snippet**: the smallest program that shows the
defect, with the expected outcome and the actual one side by side.

- **Runnable as written.** A `.py` file someone can paste into a scratch directory and run —
  `confarg`, the standard library, and (where the bug is in a front-end) that front-end. No
  pytest, no fixtures, no repository test helpers: a ticket is read cold, often by someone who
  has not cloned anything yet. A bug about import timing or module layout needs more than one
  file; show each of them under its filename, and keep each one to a handful of lines.
- **Smallest shape that still shows it.** One field where one field is enough, defaults where
  the values do not matter, `argv=[...]` and `env={...}` passed explicitly rather than assumed
  from the real environment.
- **Expected against actual, both spelled out.** Either as trailing comments, as above, or as
  two labelled lines of output when the snippet prints both halves of a parity gap. Say which
  one is which; a reader must never have to work out which line is the bug.
- **Copied from a real run, not predicted.** Paste the actual exception type and message the
  snippet produced. If you cannot run it — a front-end you have no way to invoke, a platform
  you are not on — keep the *(inferred)* marker and label the actual line as predicted, in
  those words. Never let a guessed transcript read like a transcript.
- **Running it settles the confidence marker.** If an *(inferred)* ticket reproduces, drop the
  marker in the same edit. If it does not reproduce, the ticket is wrong: correct the entry or
  delete it — do not leave a snippet on the board that nobody can make fail.
- **The snippet is not the regression test.** It goes on the board, never in `tests/`. Fixing
  the bug starts by turning it into a real test under the test-first protocol, and closing the
  ticket deletes the snippet with the rest of the entry.

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
