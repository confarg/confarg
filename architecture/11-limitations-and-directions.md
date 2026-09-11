# Limitations, open questions and directions

Update this file whenever a gap is closed or found.

## Parity gaps

Divergences between front-ends or channels that have **not** been approved as intentional.

- **Bare whole-dict flags.** `--locals VALUE` and `--<dictfield> VALUE`: vanilla reports a
  confarg error, adapters register no flag so their framework rejects the token with its own
  message ([08](08-locals.md#gap)).
- **Scalar roots on the CLI.** A non-struct target is set from argv only as
  `--<cli_prefix> VALUE`; adapters have no `cli_prefix`, so they cannot set a scalar root from
  the CLI (env and files work) ([03](03-cli-parsing.md#cli_prefix)).
- **Root JSON in the environment.** CLI `--json '{…}'` injects a whole config, but
  `_parse_env._apply_env_json_cast` declines a root-level `<PREFIX>JSON`, which is then treated
  as an unknown field. *(from code reading; not covered by a test)*
- **Completion.** argparse and click have completion helpers; cyclopts has none. Click
  completion supports bash and zsh, not fish.

## Intent versus implementation

- **Stealing rule order.** Intended: `registered leaf > Enum > [float, int, bool, None] > str`
  (confirmed by the maintainer). Implemented: `Enum > other non-str types in declaration
  order > str`, `None` and bool-vs-int handled first
  ([05](05-types-and-construction.md#stealing-rule)). Fix the code, not the tutorial.

## Known limitations

- `--config.<path>+` fragments keep references anchored at the merged root
  ([07](07-expressions.md#reference-anchoring)).
- Expressions cannot contain `}`, collection literals, slices, comprehensions or lambdas.
- Malformed expressions contribute no dependency edges (their error surfaces at validation);
  the topological sort is quadratic in the number of expressions; each expression is parsed
  several times.
- List deletion and negative indices require a base list; index-keyed lists must be gap-free
  unless the element type is Optional.
- Owning-class detection for `fn: Class.method` fails for lambdas and nested scopes; callables
  not built by confarg may not be serializable ([06](06-callables.md#round-trip)).
- Plain classes cannot be dumped with `dump()`; they must store `__init__` parameters as
  same-named attributes to serialize as fields.
- Attribute docstrings used for help need the class source (unavailable for dynamically
  created classes).
- `build_dynamic_flags` swallows every error: a broken dynamic registration only shows up as
  the framework rejecting a flag.

## Code-level warts

- The framework-neutral flag model (`FlagSpec`, `FieldMeta`, `_build.py`) lives under
  `cli/argparse/` by historical accident; it belongs in `cli/`. Refactor candidate.
- The scalar-cast table exists three times: `_cast.SCALAR_CAST_TYPES`,
  `_construct._CAST_TYPE_NAMES` and `_build._SCALAR_CAST_TYPES`. `_cast` should be the only one.
- `argparse/_register.py` keeps thin `_add_*` wrappers only for `_completion.py`; a completion
  refactor onto `FlagSpec` would remove them.
- `_import_dotted` assumes no builtin name collides with an importable module, and treats an
  `ImportError` raised *inside* a module the same as "not a module".
- `_merge.LIST_APPEND_KEY` accepts an index-keyed dict value "for future env-var support" that
  nothing produces yet.
- `tests/examples/_registry.py` describes a README replay harness (`test_readme_commands.py`)
  that no longer exists; the registry is orphaned.

## Open questions

- **Implicit subclass selection.** PR #58 inferred a subclass from CLI/file input without a
  tag; PR #63 removed implicit subclass discovery. The reason is not recorded (the commits have
  no body). Ask before reintroducing any inference.

## Possible directions

Unvetted ideas carried over from an earlier architecture review; none is decided.

1. **A registry of reserved sentinel keys** (`__root__`, `__cast__`, `__value__`, `+`, `-`, `*`,
   `~`, …) with a guard against user keys colliding with them, hardening the plain-dict IR.
2. **An explicit ordered patch-op stream** shared by vanilla and adapters, instead of re-running
   the vanilla parse loop in `patch_only` mode, making patch parity structural.
3. **Optional structural validation right after `merge()`** for earlier, better-located errors,
   without changing the merge/build contract.
4. **`Annotated` field metadata read by all three channels** (help, aliases), extending per-field
   configuration without custom types.
5. **Lazy resolution** between `merge` and `build` for very large configurations.
6. **Value provenance**: remembering which source set each value (à la Dynaconf `inspect`),
   as an opt-in richer IR.
