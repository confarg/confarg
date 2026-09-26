# REF-42 — `argparse/_completion.py` re-implements the `cli/_build.py` type walk

**Where:** `src/confarg/cli/argparse/_completion.py` (`_extend_walk_field`,
`_extend_walk_specs`) · **Filed:** 2026-09-24
**Effort:** M · **Risk:** medium · **Impact:** none

`_extend_walk_field` is branch-for-branch `_build._specs_for_field`, and `_extend_walk_specs` is
`_collect_struct_specs` — same `_resolve_struct` / `_var_params` / `_get_field_docstrings` /
`_struct_defaults` preamble, same `_is_final` unwrap, same callable, struct, dict and leaf
branches in the same order. Static flag generation is supposed to have one owner
([04-cli-adapters.md#framework-neutral-flag-model](../../architecture/04-cli-adapters.md#framework-neutral-flag-model)),
and completion quietly holds a second copy of it.

Only three things actually differ: a `_is_singleton_literal` skip, no recursion into sibling
union variants, and the `existing_dests` guards.

Take the risk-free half first — about 34 lines, no behavior change:

- the seven `if flag not in ctx.existing_dests` / `.add(flag)` pairs are redundant.
  `load_flags_into_parser` recomputes `existing_dests` from `parser._actions` and
  `_register_spec` returns early on a known dest, and duplicates within one spec list keep the
  first. `ctx.existing_dests` still has a real use in the bind-spec dedupe further down, so it
  does not go away entirely;
- `_whole_value_spec` is written out verbatim **three times inside one function**, the same
  eleven-argument call each time.

The full merge — route through `_specs_for_field` with a `concrete` switch and a
do-not-recurse-into-variants switch — is a **behavior change** unless a third switch is added: a
namedtuple field currently takes completion's `_is_struct` branch and would start receiving
`_collect_namedtuple_specs` index and name flags, i.e. more completion suggestions. Decide that
deliberately; completion must never raise
([04-cli-adapters.md#completion](../../architecture/04-cli-adapters.md#completion)).

Verified dead in the same file, and cheap to take with it: the `group_target` parameter of
`_extend_walk`, which already carries `noqa: ARG001 # kept for callers` and whose docstring says
it is ignored; and `concrete=False`, which no production caller reaches.
