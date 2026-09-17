# Boards

Open work on confarg, split into four boards. They are the standing place for
**drive-by findings**: anything you notice while doing something else and must not
silently fix, forget, or fold into an unrelated change.

| Board | Holds |
|---|---|
| [bugs/](bugs/README.md) | Things that are wrong: defects, parity gaps, code that deviates from the documented intent. |
| [features/](features/README.md) | Things that are missing: desirable behavior, and unvetted ideas worth considering. |
| [refactors/](refactors/README.md) | Things that work but should be cleaner: duplication, misplaced code, dead weight, test hygiene, performance. |
| [questions/](questions/README.md) | Things only the maintainer can settle: missing rationale, undecided trade-offs. |

The boards say *what is left to do*. `../architecture/` says *why the code is the way
it is*. A closed ticket often leaves a decision behind — the decision goes to
`../architecture/`, not here.
Boards hold open work only: a ticket's file is deleted when it closes, and its ID is named in
the revision that closed it.

## One ticket, one file

Every ticket is its own file inside its board's folder, named `<ID>-<slug>.md`:
`bugs/BUG-3-root-json-cast-refused-in-env.md`. The ID leads, because that is what code comments and
revision descriptions cite; the slug only makes a directory listing readable and may be
reworded freely. The file opens with `# <ID> — <headline>` and holds nothing else.

Each board folder also carries a `README.md`: the board's intro, and a table of its open
tickets with effort, risk and impact. **The ticket files are authoritative and the table is a
view of them**, so the table is generated, never edited. After filing, closing or re-sizing a
ticket, run:

```bash
uv run python docs-dev/todo/index.py
```

It rewrites the table between the `tickets:start` and `tickets:end` markers, leaving the prose
around them alone, and checks what it reads on the way past: a filename that disagrees with its
heading, a board holding another board's prefix, a missing or misspelled effort, risk or
impact, a bug ticket with no reproduction, and two tickets claiming one ID. `--check` writes
nothing and exits non-zero instead, which is the form for CI.

Documentation defects go on these same boards, sorted the same way: documentation wrong about
itself is a bug, documentation that is missing is a feature, documentation merely untidy is a
refactor. There is no separate documentation board, because the boards sort by *what the entry
is* and not by which files it touches — and `**Where:**` already says which files those are.

## Ticket format

````markdown
# BUG-99 — One-line summary in the imperative or as a defect statement

**Where:** `src/confarg/_parse_env.py` · **Filed:** 2026-09-12 · *(inferred — from code
reading, no test covers it)*
**Effort:** M · **Risk:** high · **Impact:** config

Two or three lines: what is wrong, when it bites, and what the fix direction looks like.
Link the rationale it touches:
[07-expressions.md#deferral-rule](../../architecture/07-expressions.md#deferral-rule).

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
  Check the board folder, not your memory — two tickets once shared REF-26.
- **Confidence**: mark anything you have not actually observed as *(inferred)*, as in the
  architecture notes. A suspicion is worth filing; a suspicion sold as a fact is not.
- **Reproduction**: every ticket on `bugs/` ends with one. See [Reproduction](#reproduction).
  The other three boards are exempt — nothing is broken yet to reproduce.
- **Effort, risk and impact**: every ticket on `bugs/`, `features/` and `refactors/` carries
  all three, on their own line under `**Where:**`. See [Effort](#effort), [Risk](#risk) and
  [Impact](#impact). `questions/` is exempt — a question is answered, not implemented.
- **Ordering**: tickets sort by ID, which is filing order, so the newest is last. There is no
  priority field — say it in the body if it matters.
- **Links** are relative to the ticket file, which sits one level deeper than the board:
  `../../architecture/…`.
- Keep it short. The code and `../architecture/` hold the detail; a ticket only has to be
  enough to pick the work up cold.

## Reproduction

A bug ticket is not filed until someone else can see the bug for themselves. Every entry on
`bugs/` therefore ends with a **reproduction**: the smallest thing someone can run that shows
the defect, with the expected outcome and the actual one side by side.

For a defect in the code, that is a **runnable snippet**:

- **Runnable as written.** A `.py` file someone can paste into a scratch directory and run —
  `confarg`, the standard library, and (where the bug is in a front-end) that front-end. No
  pytest, no fixtures, no repository test helpers: a ticket is read cold, often by someone who
  has not cloned anything yet. A bug about import timing or module layout needs more than one
  file; show each of them under its filename, and keep each one to a handful of lines.
- **Smallest shape that still shows it.** One field where one field is enough, defaults where
  the values do not matter, `argv=[...]` and `env={...}` passed explicitly rather than assumed
  from the real environment.

For a defect in the documentation itself there is no program to run, so the reproduction is the
**broken reference and what it fails to reach**: a `console` block showing the command that
finds it — a `grep`, a link check — and the target it lands on instead.

Everything below applies to both kinds.

- **Expected against actual, both spelled out.** Either as trailing comments, as above, or as
  two labelled lines of output when the snippet prints both halves of a parity gap. Say which
  one is which; a reader must never have to work out which line is the bug.
- **Copied from a real run, not predicted.** Paste the actual exception type and message the
  snippet produced. If you cannot run it — a front-end you have no way to invoke, a platform
  you are not on — keep the *(inferred)* marker and label the actual line as predicted, in
  those words. Never let a guessed transcript read like a transcript.
- **Running it settles the confidence marker.** If an *(inferred)* ticket reproduces, drop the
  marker in the same edit. If it does not reproduce, the ticket is wrong: correct the entry or
  delete it — do not leave a reproduction on the board that nobody can make fail.
- **The reproduction is not the regression test.** It stays on the board, never in `tests/`.
  Fixing the bug starts by turning it into a real test under the test-first protocol, and
  closing the ticket deletes the file it lives in.

## Effort

How much work the change is, anchored to properties of this repository rather than to hours,
which nobody can predict and which age badly:

| | |
|---|---|
| `S` | One module, mechanical. The design is obvious and the existing tests already cover the behavior. |
| `M` | A few modules, or one channel or front-end. The design is settled; the work is writing it and its tests. |
| `L` | Crosses channels or front-ends, **or** needs a new decision recorded in `../architecture/`, **or** sweeps the whole test suite. |
| `XL` | A new subsystem or a new public seam, with several design axes still open. |

An unvetted idea has no design yet, so its implementation cannot honestly be sized. Size the
**design pass** instead — deciding whether to do it at all is the next actionable step — and
say so: `**Effort:** M *(design pass; implementation not sized)*`. Size that pass by the
investigation it needs, not by the `L` clause above: a design pass always ends in a decision
record, so reading that clause literally would make every one of them `L`.

## Risk

**What catches the mistake if the change turns out to be wrong** — not how likely that is, and
not how much work it is. Read it as: how loudly does this repository fail when you get it
wrong?

| | |
|---|---|
| `low` | An existing test fails. The suite catches you before you commit. |
| `medium` | Nothing covers it yet, and a mistake stays silent in **one** channel or front-end while the others stay correct. Closing it means adding a test there. |
| `high` | Nothing covers it yet, and a mistake stays silent in **every** channel and front-end at once — the merge core, the coercion rules, the expression engine, anything under [09-invariants.md](../architecture/09-invariants.md), the [fragile couplings](../architecture/09-invariants.md#fragile-couplings) above all. Closing it means extending the cross-channel contract suite, which is what [cross-channel parity](../architecture/09-invariants.md#cross-channel-parity) demands. |

Risk and effort are independent: REF-6 is a small, obvious deletion in the merge core that
nothing covers (`S`, high), while REF-27 is a wide mechanical move of test files that the
suite catches instantly (`M`, low).

Do **not** score by how careful you intend to be, or by how small the edit looks. Two tickets
in the same module can differ honestly — REF-6 is `high` because nothing exercises the branch
it deletes, while a fully covered edit to that same file is `low`.

## Impact

**What a user of the library has to change**, assuming the change is *correct*. Risk is about
us catching a mistake; impact is about them feeling a success. The two are independent, and
the rungs run in order of how late the user finds out:

| | |
|---|---|
| `none` | Invisible to a user of the library. Internal structure, tests, internal documentation. Nothing anyone writes or runs changes. |
| `behavior` | A user sees a difference but changes nothing: a new flag or field shape becomes available, an error message improves, something that used to fail starts working. |
| `api` | A user's **code** must change — a public signature, keyword name, import path or exception type. It fails loudly, at import or under a type checker, at development time. |
| `config` | A user's **configuration** must change — a config file, environment variable or command-line invocation that works today stops working, or starts meaning something else. |

Where a change is both, take the higher rung. `config` outranks `api` deliberately: an API
break is caught by the tools a user already runs, while a config break passes every one of
them and surfaces in deployment, sometimes silently. BUG-4 (closed) is the case to keep in
mind — `int | Decimal` resolved to `5` until the documented stealing rule was honored and to
`Decimal('5')` after it, so every deployed configuration relying on the old answer changed
meaning with no error anywhere.

Impact doubles as a smell test on a refactor: anything above `none` on `refactors/` is not
really a refactor. REF-9 is `api`, which is what says it needs a deprecation story rather than
a rename.
