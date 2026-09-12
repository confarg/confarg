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

Two or three lines: what is wrong, when it bites, and what the fix direction looks like.
Link the rationale it touches: [07-expressions.md#deferral-rule](../architecture/07-expressions.md#deferral-rule).
```

- **ID**: prefix (`BUG` / `FEAT` / `REF` / `Q`) plus the next unused number on that board.
  IDs are never reused, so they stay greppable in code comments and revision descriptions.
- **Confidence**: mark anything you have not actually observed as *(inferred)*, as in the
  architecture notes. A suspicion is worth filing; a suspicion sold as a fact is not.
- **Ordering**: newest at the bottom of its section. There is no priority field — say it in
  the body if it matters.
- Keep it short. The code and `../architecture/` hold the detail; a ticket only has to be
  enough to pick the work up cold.

## Closing a ticket

Delete the entry, mention its ID in the `jj describe` message, and record any lasting
decision in `../architecture/`, as the project instructions require. Deciding *not* to do
something also closes a ticket — record that refusal and its reason in
`../architecture/10-design-decisions.md` before deleting, or the ticket will be filed again
in six months.
