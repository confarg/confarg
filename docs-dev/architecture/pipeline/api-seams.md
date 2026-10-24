# Public API seams

The API is the pipeline turned inside out; `__all__` in `confarg/__init__.py` groups it deliberately (non-alphabetical, hence `noqa: RUF022`):

| Group | Functions | Stops after |
|---|---|---|
| two-step | `merge`, `build` | collection / resolution + construction |
| three-step (dict-centric) | `merge`, `resolve(target, data)`, `from_dict` | collection / resolution / construction |
| one-step | `load` | everything |
| dump | `dump`, `dump_file` | serialization |

Shared keyword defaults and reserved key names live in `_defaults.py` so the five front-ends cannot drift.

## One option set

The keywords that say which sources to read and how — `argv`, `env`, `env_prefix`, `env_separator`, `cli_prefix`, `config_flag`, `files`, `env_config`, `union_tag` — are declared once, as the public `MergeOptions(TypedDict, total=False)` in `_defaults.py`, and every function that takes them is spelled `**opts: Unpack[MergeOptions]`: `merge`, `load`, the adapters' `merge_*` / `from_*` (REF-40), and their `populate_*` and `make_parser`, which type the flags by the sources they name, record them, and hand them to the merge (`cli._sources.reconcile`, [design decisions](../design-decisions/a-node-types-its-keys-by-the-class-it-names.md#the-adapters)).
Spelled out in each of those signatures, the set had been copied fourteen times, and its documentation had drifted — `env_prefix` read five different ways.

- **Defaults have one home.**
  A TypedDict holds no defaults, so `_defaults._resolve_options` is the one function that applies them, into the private frozen `_Options`, which is all the pipeline below the public functions reads.
  It is also where `argv` and `env` fall back to `sys.argv[1:]` and `os.environ`, a decision three call sites used to make each.
- **An unknown keyword still raises `TypeError`**, with Python's own wording: a `**opts` signature accepts any name at runtime, so `_resolve_options` refuses a key the TypedDict does not declare.
  Static checking is the type checker's — mypy, pyright and Pylance reject a misspelled keyword against `Unpack`; ty 0.0.84 checks the value types but not the names.
- **`cli_prefix` is `str | None` for everyone.**
  Omitted means "the prefix the flags were registered under": the one `populate_*` recorded for an adapter (`cli._prefix.resolve_prefix`), none for vanilla, which registers nothing.
  Vanilla used to type it `str = ""`; accepting `None` there is the only widening, and it buys one option set instead of a base and two variants.
  The `populate_*` functions and `make_parser` take the same set, so they default it to `None` too (REF-9, [design decision](../design-decisions/adapter-argument-names-keep-the-framework-noun.md)): `None` and `""` both register no prefix.
- **The documentation moved.**
  The reference page renders `**opts` on each function and the per-key table once, on `MergeOptions`, from the attribute docstrings.
  A caller passes the same keywords as before, and can annotate a forwarding wrapper with the public type.

Rejected: keeping the fourteen explicit signatures and sharing only their prose, the way httpx and FastAPI repeat parameters on every entry point and pandas and matplotlib share docstring text by substitution.
It keeps `help()` and `inspect.signature` listing the names, but every signature is still a copy a new keyword has to be added to.
The precedents for the chosen shape are pydantic's `ConfigDict` and pydantic-settings' `SettingsConfigDict` (options as a public TypedDict) and PEP 692's own motivating case.
Also set aside: an options *object* passed as one argument, which would change every call site where this keeps every one of them as it was.

**Round-trip fidelity comes from the seam, not from a reverse pass.**
The two dumps write two different things ([design decision](../design-decisions/the-object-dump-writes-state.md#the-object-dump-writes-state)).
`merge()` keeps `${...}` and every callable spec verbatim and `dump_file(raw_dict, path)` writes them back, so a merged config can be saved as written: how its values are produced.
`dump(instance)` serializes the *constructed* object, the values the program ran with: every expression resolved, and every `call:` replaced by what it produced.
There is deliberately no "un-resolve" step.

**The field defaults enter after `merge()`.**
`build()`, `resolve()` and `from_dict()` lay the target's defaults under the data, so a `merge()` result holds only what the sources said, and a saved merge keeps following the class's defaults; `resolve()` takes the target for that reason ([design decisions](../design-decisions/a-field-default-is-the-base-layer.md#a-field-default-is-the-base-layer)).

The raw dict is made of file-native values: `_try_coerce` coerces a CLI, env or CSV token eagerly only to a value a file holds natively, and leaves an `Enum` or registered leaf as typed ([types](../types/token-model.md#a-leaf-reaches-the-merged-dict-as-written)), so `merge()` reads back unchanged from its own dump (BUG-246).
A dict a caller builds may still hold a `Path` or an `Enum` member that no config-file writer accepts, so `dump_file` applies the same leaf rules as `dump()` — `_serialize_untyped` walks the containers and hands every leaf to `_serialize_leaf` ([types](../types/serialization.md#serialization)) — rather than unwrapping `_StrToken` alone.
Such a leaf is written in its scalar form, exactly as the same key would have been written had a file supplied it.

**Such an object round-trips at `build()`, not as a dict.**
Re-reading the dump yields the plain scalar, because file values are never re-interpreted ([types](../types/token-model.md#token-model)): the dicts differ, while the built objects are equal.
Re-coercing on read-back to close that gap was rejected ([design decisions](../design-decisions/dump-round-trips-at-the-built-object.md#dump-round-trips-at-the-built-object)).

`dump()` accepts a dataclass or a plain-class instance, a plain class read by its constructor's parameters; one whose state does not mirror them is refused naming the merged dict, which keeps the arguments as given ([the object dump is forensic](../design-decisions/the-object-dump-writes-state.md#the-object-dump-is-forensic)).
