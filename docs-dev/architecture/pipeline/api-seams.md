# Public API seams

The API is the pipeline turned inside out; `__all__` in `confarg/__init__.py` groups it
deliberately (non-alphabetical, hence `noqa: RUF022`):

| Group | Functions | Stops after |
|---|---|---|
| two-step | `merge`, `build` | collection / resolution + construction |
| three-step (dict-centric) | `merge`, `resolve`, `from_dict` | collection / resolution / construction |
| one-step | `load` | everything |
| dump | `dump`, `dump_file` | serialization |

Shared keyword defaults and reserved key names live in `_defaults.py` so the five front-ends
cannot drift.

**Round-trip fidelity comes from the seam, not from a reverse pass.** `merge()` keeps
`${...}` verbatim and `dump_file(raw_dict, path)` writes it back, so a merged config can be
saved with its expressions. `dump(instance)` serializes the *constructed* object and
therefore emits resolved values. There is deliberately no "un-resolve" step.

The raw dict is not made of file-native values, though: `_try_coerce` coerces CLI, env and
CSV leaves eagerly ([CLI parsing](../cli-parsing/token-consumption.md#token-consumption)), so it can hold a `Path` or an
`Enum` member that no config-file writer accepts. `dump_file` therefore applies the same leaf
rules as `dump()` — `_serialize_untyped` walks the containers and hands every leaf to
`_serialize_leaf` ([types](../types/serialization.md#serialization)) — rather than unwrapping
`_StrToken` alone. A coerced leaf is written in its scalar form, exactly as the same key would
have been written had a file supplied it, which is what keeps the channels equivalent.

**A coerced leaf therefore round-trips at `build()`, not at `merge()`.** Re-reading the dump
yields the plain scalar, because file values are never re-interpreted
([types](../types/token-model.md#token-model)): `merge() != merge(dumped)` for such a key,
while `build(merge()) == build(merge(dumped))`. Re-coercing on read-back to close that gap
was rejected ([design decisions](../design-decisions/dump-round-trips-at-the-built-object.md#dump-round-trips-at-the-built-object)).

`dump()` accepts dataclass instances only; plain classes cannot be dumped reliably (their
state is not guaranteed to mirror `__init__`), so the error message steers users to dumping
the merged dict instead.
