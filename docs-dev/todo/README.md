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
reworded freely. The file opens with its [front matter](#front-matter), then
`# <ID> — <headline>`, and holds nothing else.

Each board folder also carries a `README.md`: the board's intro, and a table of its open
tickets with severity, blockers, effort, risk and impact, sorted in [work order](#work-order).
**The ticket files are authoritative and the table is a
view of them**, so the table is generated, never edited. After filing, closing or re-sizing a
ticket, run:

```bash
uv run python docs-dev/todo/index.py
```

It rewrites the table between the `tickets:start` and `tickets:end` markers, leaving the prose
around them alone, and checks what it reads on the way past: a filename that disagrees with its
heading, a board holding another board's prefix, a missing, unknown or misspelled front matter
field, a bug ticket with no reproduction or no [origin](#origin), two tickets claiming one ID, a
`where` naming a file or symbol that no longer exists, and a `blocked_by` naming a ticket that is
closed or closing a cycle. Validation
gates the rewrite: one error anywhere leaves **every** table exactly as it was, because a table
written beside an error is a table missing the row of a ticket that is still open. Fix what it
reports, then run it again. `--check` writes nothing either way and exits non-zero on a stale
table, which is the form for CI.

`--where PATH` answers the question to ask before editing a file: which open tickets touch it?
It matches a ticket filed against that file, against a directory above it, against a file below
it when `PATH` is a directory, or through a glob:

```console
$ uv run python docs-dev/todo/index.py --where src/confarg/_parse_env.py
bugs/BUG-115-every-prefixed-env-var-overwrites-a-scalar-root.md
  BUG-115 — Every prefixed environment variable overwrites a scalar root
  where: src/confarg/_parse_env.py::_parse_env
…
```

`--next [N]` answers the question to ask before picking work up: what comes first? It prints the
first `N` (10 by default) unblocked tickets across every board, in [work order](#work-order):

```console
$ uv run python docs-dev/todo/index.py --next 1
 1. BUG-115 — Every prefixed environment variable overwrites a scalar root
    critical · S · bugs/BUG-115-every-prefixed-env-var-overwrites-a-scalar-root.md
```

Documentation defects go on these same boards, sorted the same way: documentation wrong about
itself is a bug, documentation that is missing is a feature, documentation merely untidy is a
refactor. There is no separate documentation board, because the boards sort by *what the entry
is* and not by which files it touches — and `where` already says which files those are.

## Ticket format

````markdown
---
filed: 2026-09-12
where:
  - src/confarg/_parse_env.py::_parse_env  # the `if not is_struct:` branch
effort: M
risk: high
impact: config
severity: critical
inferred: true  # from code reading, no test covers it
introduced_by: [BUG-12]  # PR-87, the branch that skips a non-struct root
---
# BUG-99 — One-line summary in the imperative or as a defect statement

Two or three lines: what is wrong, when it bites, and what the fix direction looks like.
Link the rationale it touches:
[expressions/deferral-rule.md#deferral-rule](../architecture/expressions/deferral-rule.md#deferral-rule).

Origin: regression from the fix for BUG-12, which let a scalar root take its value from the
environment and kept the same branch for every prefixed variable, matched or not.

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
  architecture notes — the ticket as a whole with `inferred: true`, a single claim in the body
  with the inline marker. A suspicion is worth filing; a suspicion sold as a fact is not.
- **Origin**: every ticket on `bugs/` names the revision that introduced the bug, and says why it
  did. See [Origin](#origin).
- **Reproduction**: every ticket on `bugs/` ends with one. See [Reproduction](#reproduction).
  The other three boards are exempt — nothing is broken yet to reproduce.
- **Effort, risk, impact and severity**: every ticket on `bugs/`, `features/` and `refactors/`
  carries all four. See [Effort](#effort), [Risk](#risk), [Impact](#impact) and
  [Severity](#severity). `questions/` is exempt — a question is answered, not implemented.
- **Ordering**: there is no priority field. The tables sort in [work order](#work-order), which
  `index.py` derives from severity, `blocked_by` and effort.
- **Links** are relative to the ticket file, which sits one level deeper than the board:
  `../../architecture/…`.
- Keep it short. The code and `../architecture/` hold the detail; a ticket only has to be
  enough to pick the work up cold.

## Front matter

Every ticket opens with YAML front matter between two `---` lines. It holds the fields a script
reads — to build the tables, to answer `--where`, to catch a ticket orphaned by a rename — and
nothing else: the ID and headline are the filename and the heading, and everything a reader
needs beyond the fields is the body. A value is bare; what qualifies it goes in a YAML comment
on the same line, where the parser drops it and a reader still sees it.

| Key | Boards | Value |
|---|---|---|
| `filed` | all, required | The filing date, `YYYY-MM-DD`. |
| `where` | all | A list of repository-root paths the work touches, each optionally followed by `::` and a symbol the file defines (`src/confarg/_files.py::_dump_yaml`, as pytest spells a node). A directory ends with `/`; a glob (`src/confarg/cli/*/_register.py`) must match a file. `where: []  # a new console script` when the code does not exist yet. |
| `effort` | sized, required | `S`, `M`, `L` or `XL` — see [Effort](#effort). |
| `risk` | sized, required | `low`, `medium` or `high` — see [Risk](#risk). |
| `impact` | sized, required | `none`, `behavior`, `api` or `config` — see [Impact](#impact). |
| `severity` | sized, required | `critical`, `major`, `minor` or `trivial` — see [Severity](#severity). |
| `needs_design` | sized | `true` when the effort sizes the design pass, not the implementation — see [Effort](#effort). Omitted otherwise. |
| `inferred` | all | `true` when the ticket rests on something nobody observed; the comment says what it rests on. Omitted otherwise. |
| `blocked_by` | all | A list of open ticket IDs that must close first, on any board. Omitted when empty. |
| `introduced_by` | bugs, required since 2026-10-07 | The revision that introduced the bug: a list of the ticket IDs it closed, open or not, or `PR-<n>` when it closed none, or `unknown` with a comment saying what was searched — see [Origin](#origin). |

`where` is checked against the tree: a path that no longer exists or a symbol its file no longer
holds is an error, so a rename that orphans a ticket is caught by the next run. The
agent-facing files (`AGENTS.md`, `CLAUDE.md`, `docs-agents/`) are exempt, since version control
ignores them. A `blocked_by` entry whose ticket has closed is an error too: that ticket is
unblocked, so drop the entry; so is a cycle of `blocked_by` entries, which nothing could ever
start. Any other key is refused — there is deliberately no `id`, `title`, `status`, `priority`
or `labels`. A priority especially is computed, never written: see [Work order](#work-order).

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
finds it — a `grep`, a link check — and the target it lands on instead. That block never
executes: `docs-dev/` is excluded from pytest collection
([testing.md#examples-and-documentation](../architecture/testing.md#examples-and-documentation)),
so paste the real output rather than expecting a run to replay it.

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

## Origin

A bug ticket says **which revision introduced the bug, and why**. A fix aimed at the symptom
alone can land in three wrong places, and the origin is what shows them:

- **The change that introduced the bug was wrong**, and the right fix is to revert or rework
  it rather than to patch around it.
- **One change introduced several bugs.** Fixed one by one, each fix is narrow and the next
  ticket still stands; fixed at their shared origin, they close together.
- **Two fixes undo each other.** A bug introduced by the fix for another means the two
  constraints meet at one place in the code. Fixed independently, each fix brings the other
  bug back in a new shape, and only a change that honors both at once ends the loop.

**Finding it.** Start from the code the bug runs through: read who wrote those lines
(`jj file annotate`, `git blame`), then search the history for when the deciding line or the
missing branch appeared (`jj log -r 'diff_lines(substring:"…", "path")'`, `git log -S`). When the
cause is spread out, bisect: run the reproduction against older revisions until it stops failing
(`jj bisect run`, `git bisect run`). Then read the revision found — its description, its diff and
the ticket it closed — until you can say what it set out to do and why that produced the bug.

**Naming it** in `introduced_by`:

- **The ticket IDs the revision closed**, which its description cites (`fix(cli): … (BUG-97)`).
  It is usually closed by now; that is expected.
- **`PR-<n>`** when it closed none: every revision on `master` carries the number of the pull
  request that merged it (`feat: Add cyclopts integration (#26)` is `PR-26`).
- **Never a commit ID.** A rebase rewrites it, and a squash merge replaces every commit of a
  pull request with one new one, so it names nothing a month later.
- **Several entries** when the bug took more than one revision to appear, and **`unknown`** when
  the search came back empty, with a YAML comment saying what was searched. `unknown` is an
  answer; an absent key is a ticket nobody researched.

The YAML comment on the line carries the PR number or the code involved. The body carries the
**why**, in an `Origin:` paragraph: what that revision meant to do, and how it produced the bug.
Say whether the bug is a **regression** — it worked before that revision, so the revision broke
it — or **latent** — wrong since the code was first written, so the revision is where the case
was missed. A regression introduced by a bug fix gets the closest look, since that is the
pattern of the third case above.

**Bugs sharing an origin** share a value in the *Introduced by* column of the
[bugs table](bugs/README.md): grep the table for an ID to find them.

**After the fix.** Closing the ticket deletes the file, and the origin with it, so the
description of the revision that fixes the bug keeps it, as a trailer on the last line:

```text
fix(env): Match a prefixed variable against the root before setting it (BUG-115)

Introduced-by: BUG-12
```

`Introduced-by: unknown` when the ticket said so. The history then answers both questions: what
did this revision fix (its subject), and what did a revision break (the trailers naming it):

```console
$ jj log -r 'description(substring:"Introduced-by: BUG-12")'
$ git log --grep='Introduced-by: BUG-12'
```

A bug filed before this rule took effect, on 2026-10-07, may carry no `introduced_by` until a
sweep reaches it; `index.py` requires one on every bug filed since.

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
say so with `needs_design: true` beside the effort. Size that pass by the investigation it
needs, not by the `L` clause above: a design pass always ends in a decision record, so reading
that clause literally would make every one of them `L`.

## Risk

**What catches the mistake if the change turns out to be wrong** — not how likely that is, and
not how much work it is. Read it as: how loudly does this repository fail when you get it
wrong?

| | |
|---|---|
| `low` | An existing test fails. The suite catches you before you commit. |
| `medium` | Nothing covers it yet, and a mistake stays silent in **one** channel or front-end while the others stay correct. Closing it means adding a test there. |
| `high` | Nothing covers it yet, and a mistake stays silent in **every** channel and front-end at once — the merge core, the coercion rules, the expression engine, anything under [invariants.md](../architecture/invariants.md), the [fragile couplings](../architecture/invariants.md#fragile-couplings) above all. Closing it means extending the cross-channel contract suite, which is what [cross-channel parity](../architecture/invariants.md#cross-channel-parity) demands. |

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

## Severity

**What a user meets while the ticket stays open.** Effort, risk and impact all describe the
change; severity describes the problem as it stands, and is the cost of leaving it there. The
rungs run as impact's do, in order of how late the user finds out:

| | |
|---|---|
| `critical` | **A wrong result with no error.** A configuration loads and means something other than it says — a value misread, dropped or left uncoerced, one front-end meaning what the others do not — or a configuration can exhaust the host. Nothing in the user's tooling catches it. BUG-115, BUG-146, BUG-155. |
| `major` | **A valid use fails loudly, with no workaround.** A configuration or flag that should work is refused, or crashes with a raw Python exception instead of a confarg error, or a front-end cannot register the target at all. BUG-114, BUG-117, BUG-152. |
| `minor` | **Slowed, not stopped.** A loud failure with a workaround, invalid input answered with a raw exception or a misleading message, a wrong usage or help line, a missing convenience. BUG-144, BUG-154, BUG-176. |
| `trivial` | **No user of the library meets it.** Internal documentation, test hygiene, code structure. BUG-119, BUG-149. |

Score what the user meets, not how often: frequency is a guess, the symptom is in the
reproduction. A feature's severity is what its *absence* costs — FEAT-14 is `major`, because an
ordinary dataclass field crashes `build()` today. A refactor is almost always `trivial`; when one
matters, it is because it blocks something that does, and the [work order](#work-order) carries
that through `blocked_by` without anyone re-scoring it.

## Work order

There is no priority field: `index.py` derives the order, and both the tables and `--next` read
it.

1. **Effective severity**, highest first. A ticket's effective severity is its own, or the
   highest effective severity among the tickets it blocks, transitively and across boards —
   a refactor blocking a `critical` bug is `critical`, shown as `critical (via BUG-…)`. A
   question carries no severity of its own and only ever inherits one.
2. **Unblocked before blocked**: a ticket whose `blocked_by` is empty can start now.
3. **Effort**, smallest first: among equally severe tickets, the cheapest one buys the most.
4. **ID**, which is filing order.

Derived and not written, because a stored priority goes stale the moment *another* ticket gains
or loses a blocker — the drift the generated tables exist to prevent. The rationale and its
precedents are in
[design-decisions/ticket-severity-and-work-order.md](../architecture/design-decisions/ticket-severity-and-work-order.md).
