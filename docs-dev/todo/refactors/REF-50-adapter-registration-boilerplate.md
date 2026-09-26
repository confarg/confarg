# REF-50 — Adapter registration and completion boilerplate

**Where:** `src/confarg/cli/*/_register.py`, `src/confarg/cli/*/_completion.py`,
`src/confarg/cli/_clicklike/` · **Filed:** 2026-09-24
**Effort:** M · **Risk:** low · **Impact:** none

Five findings in the registration half of the adapters, about 65 lines together. The last one is
the reason to do it: the others are boilerplate, that one is a decision made four times.

- The five-step `populate_*` body — default `argv`, `build_static_flags`, load, then
  `build_dynamic_flags`, load — is written three times (argparse, `_clicklike`, cyclopts), with the
  same six keywords spelled twice per site. A shared helper returning the concatenated spec list,
  which cyclopts already builds, leaves one `load_*` call per adapter. Behavior-identical: the
  loaders dedupe by name and create groups lazily, so one pass over the concatenation equals two
  passes.
- `if argv is None: argv = sys.argv[1:]` is written out in four `_register.py` modules; letting
  `_clicklike.populate_command` accept `None` removes two of them.
- `cli/click/_completion.py` and `cli/typer/_completion.py` differ in 23 of 53 and 52 lines, and
  the only real difference is the option factory passed through — which
  `_clicklike.setup_completion` already takes as a parameter. Same case as
  [REF-41](REF-41-click-and-typer-context-are-the-same-file.md), same invariant.
- Inside the shared layer itself: `_clicklike/_context.py` defines `registered_prefix(ctx)`, and
  `_clicklike/_completion.py` re-implements the identical `PREFIX_ATTR` scan inline. One canonical
  place, broken inside the module whose whole purpose is to be that place.
- Each adapter re-derives the flag *shape* from `(nargs, whole_value)`: the `nargs == 0`
  value-less test in three places, and the `nargs == "*"` / `isinstance(nargs, int)` split in three
  more, each expressed in its framework's own vocabulary. The neutral model is supposed to be the
  contract
  ([04-cli-adapters.md#framework-neutral-flag-model](../../architecture/04-cli-adapters.md#framework-neutral-flag-model)),
  so the *classification* belongs on `FlagSpec` in `cli/_spec.py` and only the *expression* of it
  belongs in each adapter. This is where the four will drift, and it already shows: cyclopts
  silently honours no `FlagSpec.completer` at all.

Verified dead in the same area: an unused `action = target.add_argument(...)` assignment in the
value-less branch of `argparse/_register.py`; the `option_cls` parameter of
`_clicklike/_register.py`, which exists only for an `isinstance` filter that a `hasattr` on the
mixin attribute answers identically; and `_build._escaped_opener_name`, which rebuilds per call a
mapping already encoded in `_OPENER_SPECS`.
