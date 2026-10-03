# REF-42 — `argparse/_completion.py` re-implements the `cli/_build.py` type walk

**Where:** `src/confarg/cli/argparse/_completion.py` (`_extend_walk_field`,
`_extend_walk_specs`) · **Filed:** 2026-09-24
**Effort:** M · **Risk:** medium · **Impact:** none

`_extend_walk_field` is branch-for-branch `_build._specs_for_field`, and `_extend_walk_specs` is
`_collect_struct_specs` — same `_resolve_struct` / `_var_params` / `_get_field_docstrings` /
`_struct_defaults` preamble, same `_is_final` unwrap, same callable, struct, dict and leaf
branches in the same order. Static flag generation is supposed to have one owner
([cli-adapters/flag-model.md#framework-neutral-flag-model](../../architecture/cli-adapters/flag-model.md#framework-neutral-flag-model)),
and completion quietly holds a second copy of it.

Only three things actually differ: a `_is_singleton_literal` skip, no recursion into sibling
union variants, and the `existing_dests` guards.

A mutation run over `src/confarg` (2026-09-26) measured the cost of the second copy: the two
twinned functions are the weakest-tested in their respective modules — `_extend_walk_field` has 89
surviving mutants and `_specs_for_field` 87, and `cli/argparse/_completion.py` scores 52% against
`cli/_build.py`'s 64%. It also confirmed the redundancy claimed below: mutating any *single*
`ctx.existing_dests.add(flag)` site to `add(None)` survives the whole suite, while mutating all
seven at once fails 4 tests — each guard is individually non-load-bearing, exactly as argued.
One caveat for whoever picks this up: 77 of `_specs_for_field`'s 87 survivors are help-text and
`metavar` arguments, which nothing asserts anywhere, so the mutation score will stay low after the
merge and is not the measure of success here.

Take the risk-free half first — about 34 lines, no behavior change:

- the seven `if flag not in ctx.existing_dests` / `.add(flag)` pairs are redundant.
  `load_flags_into_parser` recomputes `existing_dests` from `parser._actions` and
  `_register_spec` returns early on a known dest, and duplicates within one spec list keep the
  first. `ctx.existing_dests` still has a real use in the bind-spec dedupe further down, so it
  does not go away entirely;
- `_whole_value_spec` is written out verbatim **three times inside one function**, the same
  eleven-argument call each time.

The full merge — route through `_specs_for_field` with a `concrete` switch and a
do-not-recurse-into-variants switch — is a **behavior change** in two places, because the two
walks ask the shape predicates differently. Completion has no namedtuple branch: `_is_struct` is
False for a tuple subclass, so a namedtuple field falls through to the leaf branch and gets only
its whole-value flag, while registration adds `_collect_namedtuple_specs`' index and name flags.
Completion also has no registered-leaf branch before `_is_struct`, so it opens a registered leaf
with `__init__` parameters as a struct and offers one flag per parameter. Registration gives such
a leaf only its scalar flag, and its parameter flags exist only once typed
([static-and-dynamic-flags.md](../../architecture/cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags)).
Observed 2026-10-03, with `UUID` registered and a variant `Cat` holding `id: UUID` and
`pos: Pt` (a two-field namedtuple):

```text
completion  : ['pet.id', 'pet.id.bytes', 'pet.id.bytes_le', 'pet.id.fields', 'pet.id.hex', 'pet.id.int', 'pet.id.is_safe', 'pet.id.version', 'pet.pos']
registration: [..., 'pet.id', 'pet.pos', 'pet.pos.-1', 'pet.pos.-2', 'pet.pos.0', 'pet.pos.1', 'pet.pos.x', 'pet.pos.y']
```

Decide both deliberately; completion must never raise
([cli-adapters/completion.md#completion](../../architecture/cli-adapters/completion.md#completion)).
Whichever way it goes, the merged walk should dispatch on `typedload._coerce._type_kind`, as
construction, serialization and the CLI walk do since REF-47, rather than keep a chain of its own
([types/introspection.md#shape-dispatch](../../architecture/types/introspection.md#shape-dispatch)).
`_specs_for_field` and `_extend_walk_field` are the two full shape dispatches that do not yet.

Verified dead in the same file, and cheap to take with it: the `group_target` parameter of
`_extend_walk`, which already carries `noqa: ARG001 # kept for callers` and whose docstring says
it is ignored; and `concrete=False`, which no production caller reaches.
