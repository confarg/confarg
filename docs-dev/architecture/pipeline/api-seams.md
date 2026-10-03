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

## One option set

The keywords that say which sources to read and how — `argv`, `env`, `env_prefix`,
`env_separator`, `cli_prefix`, `config_flag`, `files`, `env_config`, `union_tag` — are declared
once, as the public `MergeOptions(TypedDict, total=False)` in `_defaults.py`, and every function
that takes them is spelled `**opts: Unpack[MergeOptions]`: `merge`, `load` and the adapters'
`merge_*` / `from_*` (REF-40). Spelled out in each of those signatures, the set had been copied
fourteen times, and its documentation had drifted — `env_prefix` read five different ways.

- **Defaults have one home.** A TypedDict holds no defaults, so `_defaults._resolve_options` is
  the one function that applies them, into the private frozen `_Options`, which is all the
  pipeline below the public functions reads. It is also where `argv` and `env` fall back to
  `sys.argv[1:]` and `os.environ`, a decision three call sites used to make each.
- **An unknown keyword still raises `TypeError`**, with Python's own wording: a `**opts`
  signature accepts any name at runtime, so `_resolve_options` refuses a key the TypedDict does
  not declare. Static checking is the type checker's — mypy, pyright and Pylance reject a
  misspelled keyword against `Unpack`; ty 0.0.84 checks the value types but not the names.
- **`cli_prefix` is `str | None` for everyone.** Omitted means "the prefix the flags were
  registered under": the one `populate_*` recorded for an adapter
  (`cli._prefix.resolve_prefix`), none for vanilla, which registers nothing. Vanilla used to
  type it `str = ""`; accepting `None` there is the only widening, and it buys one option set
  instead of a base and two variants.
- **The documentation moved.** The reference page renders `**opts` on each function and the
  per-key table once, on `MergeOptions`, from the attribute docstrings. A caller passes the
  same keywords as before, and can annotate a forwarding wrapper with the public type.

Rejected: keeping the fourteen explicit signatures and sharing only their prose, the way httpx
and FastAPI repeat parameters on every entry point and pandas and matplotlib share docstring
text by substitution. It keeps `help()` and `inspect.signature` listing the names, but every
signature is still a copy a new keyword has to be added to. The precedents for the chosen shape
are pydantic's `ConfigDict` and pydantic-settings' `SettingsConfigDict` (options as a public
TypedDict) and PEP 692's own motivating case. Also set aside: an options *object* passed as one
argument, which would change every call site where this keeps every one of them as it was.

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
