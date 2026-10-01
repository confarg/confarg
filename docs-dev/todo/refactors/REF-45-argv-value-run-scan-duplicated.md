# REF-45 — The argv value-run scan is written seven times

**Where:** `src/confarg/_parse_cli.py`, `src/confarg/cli/_prefix.py` · **Filed:** 2026-09-24
**Effort:** M · **Risk:** high · **Impact:** none

`while i < len(args) and not _looks_like_flag(args[i])` appears at six places in `_parse_cli.py`
and once in `cli/_prefix.strip_argv_prefix`.

One helper absorbs all of them: `_value_run(args, i)`, returning the tokens and the new index.

The guard half is **done**: BUG-43 extracted `_parse_cli._require_value` and
`ConfargError.missing_value`, and every site that raised the message by hand — four in
`_parse_cli.py`, one with the `'<json>'` wording, one in the adapters' since-deleted collector —
goes through them.
`_require_value` is now in the canonical table; `_value_run` is what is left.

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
[invariants.md#delegate-to-the-canonical-function](../../architecture/invariants.md#delegate-to-the-canonical-function),
even though `_looks_like_flag` — the sole flag/value discriminator it is built on — is. Adding it
there is part of closing this.

BUG-43 is what the duplication already cost: the fixed-arity tuple branch was the one place the
guard had never been copied to, so that flag under-filled instead of reporting a missing value.
It is closed, and so is the adapters' half of the same gap, BUG-58 (no link: the board holds
open work only).

One pair is a duplicated *consumer* rather than a duplicated loop: cyclopts' pre-parse refusal
`_parse_cli._collect_config_file_pairs` repeats `_consume_config_paths` token for token.
BUG-50/51 moved the message builder (`_missing_config_path_msg`) and the subpath check
(`_check_mount_subpath`) into shared functions, but the consumption is still written twice. The
rescan should call `_consume_config_paths` instead, which leaves one loop for `_value_run` to
absorb.
