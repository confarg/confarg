# REF-53 — Nine `try`/`except`/`pass` blocks that `contextlib.suppress` already spells

**Where:** `src/confarg/_parse_cli.py`, `src/confarg/_parse_env.py`, `src/confarg/cli/_build.py`,
`src/confarg/cli/_collect.py`, `src/confarg/dictexpr/_expressions.py` · **Filed:** 2026-09-24
**Effort:** S · **Risk:** low · **Impact:** none

`contextlib.suppress` is already the house idiom — `cli/_build.py:311,389,559`,
`_callable.py:321,637`, `_tags.py:51,58,200` — but nine sites still write the loop by hand:

| Site | Suppressed |
|---|---|
| `_parse_cli.py:573` (`_parse_flag_mode`) | `ValueError` |
| `_parse_env.py:138` (`_match_namedtuple_part`) | `ValueError` |
| `_parse_env.py:154` (`_match_tuple_part`) | `ValueError` |
| `_parse_env.py:349` (`_store_env_value`) | `json.JSONDecodeError` |
| `cli/_build.py:409`, `:421` (`_collect_callable_field_specs`) | `SymbolImportError` |
| `cli/_collect.py:387`, `:422` | `SymbolImportError, TypeError, ValueError, NameError, AttributeError` |
| `dictexpr/_expressions.py:456` (`_eval_attribute`) | `MissingReferenceError` |

Ruff cannot see any of them: `SIM105` fires only when the `try` body is a **single simple
statement**, and every one of these has either several statements or a `return`. A `return`
inside the body is fine — it propagates normally out of a `with`. `cli/_build.py` already
imports `contextlib`; `cli/_collect.py` and `_parse_env.py` would each need the import.

One site is not a straight swap: at `_parse_env.py:349` the `try` also spans the `_set_nested`
call, so wrapping the block widens the guarded region. Hoist that call out of the `with`, or
leave the site alone and say so in the revision.

Related: ruff's preview `PLW0717` (too-many-statements-in-try-clause) flags four of these for
the same underlying reason. See the closing note in
[REF-57](REF-57-small-stdlib-swaps-in-the-core.md) on enabling it.
