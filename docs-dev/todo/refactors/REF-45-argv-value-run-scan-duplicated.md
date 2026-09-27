# REF-45 — The argv value-run scan and its missing-value guard are written seven and five times

**Where:** `src/confarg/_parse_cli.py`, `src/confarg/cli/_prefix.py`,
`src/confarg/cli/_collect.py` · **Filed:** 2026-09-24
**Effort:** M · **Risk:** high · **Impact:** none

`while i < len(args) and not _looks_like_flag(args[i])` appears at six places in `_parse_cli.py`
and once in `cli/_prefix.strip_argv_prefix`. The guard that follows it —
`if i >= len(args) or _looks_like_flag(args[i]): raise ... Missing value for ...` — appears four
times in `_parse_cli.py`, once more with different wording, and the message string a fifth time
in `cli/_collect.py`.

Two helpers absorb all of them: `_value_run(args, i)` returning the tokens and the new index, and
`_require_value(args, i, token)` raising the one canonical message.

A mutation run over `src/confarg` (2026-09-26) found a second, sharper argument for the helpers:
these hand-written `i`-advancing loops are the only place in the library where a one-token
mutation produces an *unbounded* loop rather than a wrong answer. Turning a single `i += 1` into
`i -= 1` makes the scan append forever — one mutant of `_parse_cli._collect_config_file_pairs`
reached 8.6 GB of resident memory before it was killed, and four mutants of
`cli/_prefix.strip_argv_prefix` passed 1.2 GB each. Nothing in the loops guarantees the index
advances. A shared `_value_run` puts that guarantee in one place where it can be stated once and
tested once.

Worth stating plainly, because it is the reason the risk is **high**: *"where does this flag's
value run end?"* is one of the core CLI decisions and it is **not** in the canonical table in
[09-invariants.md#delegate-to-the-canonical-function](../../architecture/09-invariants.md#delegate-to-the-canonical-function),
even though `_looks_like_flag` — the sole flag/value discriminator it is built on — is. Adding it
there is part of closing this.

[BUG-43](../bugs/BUG-43-fixed-tuple-flag-skips-the-missing-value-check.md) is what the
duplication already cost: the fixed-arity tuple branch is the one place the guard was never
copied to, so that flag under-fills instead of reporting a missing value. Fix the bug by adding
the branch to the shared helper, not by writing a fifth copy.
