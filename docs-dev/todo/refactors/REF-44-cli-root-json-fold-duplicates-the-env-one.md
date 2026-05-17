# REF-44 — The CLI root `--json` fold duplicates `_parse_env._fold_root_json`

**Where:** `src/confarg/_parse_cli.py` (end of the main loop), `src/confarg/_parse_env.py`
(`_fold_root_json`), `src/confarg/cli/_collect.py` (`apply_root_json`) · **Filed:** 2026-09-24
**Effort:** S · **Risk:** low · **Impact:** none

The five lines that fold root-level JSON casts in under the per-field values at the end of
`_parse_cli` are line-for-line the body of `_parse_env._fold_root_json`, whose own docstring
describes it as "mirroring the CLI's root `--json`" — the mirror is admitted in writing. The CLI
parser should simply call it. The root cast is one rule shared by two channels
([03-cli-parsing.md#force-casts](../../architecture/03-cli-parsing.md#force-casts)), and
`_cast.py` already owns what the cast names are and what value each produces, so the *fold* is
the one piece left with two implementations.

The "structured target" error message that goes with it is triplicated verbatim across
`_parse_cli.py`, `_parse_env.py` and `cli/_collect.py` — that half belongs to
[REF-51](REF-51-error-messages-outside-the-factories.md).

Open part, to settle before the three collapse: the scalar-root sink is a plain assignment to
`ROOT_KEY` in the vanilla CLI parser and `setdefault` in the other two. Whether a later root
value replaces or yields is an undocumented divergence; whichever way it goes, record it in
[02-files-and-env.md#environment-parsing](../../architecture/02-files-and-env.md#environment-parsing).
