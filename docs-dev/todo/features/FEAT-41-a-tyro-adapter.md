---
filed: 2026-10-10
where:  # plus a new package, src/confarg/cli/tyro/
  - src/confarg/cli/_collect.py::_merge_from_flat
  - src/confarg/cli/_spec.py::FlagSpec
  - tests/_loaders.py
  - tests/cli/test_backend_contract.py
  - pyproject.toml
effort: M  # the design pass: feasibility is probed (tyro 1.0.16, both backends), the API shape and three divergences are open
risk: medium  # a fifth front-end; a mistake stays silent in it alone until the contract suite runs it
impact: behavior
severity: minor  # workaround: confarg.load(), or one of the four existing adapters
needs_design: true  # the effort sizes the design pass; the implementation is not sized
---
# FEAT-41 — A tyro adapter

A tyro application cannot keep tyro and hand one parameter's configuration to confarg. A probe against tyro 1.0.16 found no technical blocker: the adapter fits [the adapter model](../../architecture/cli-adapters/model.md#argv-is-the-only-writer) on tyro's public API, with the same synthetic signature the cyclopts adapter builds ([framework specifics](../../architecture/cli-adapters/framework-specifics.md#cyclopts-parameter-names)).

## What the probe established

The user annotates the parameter, and the type stays the user's class for a type checker:

```python
def main(cfg: Annotated[Cfg, tyro.conf.arg(constructor_factory=<made by confarg>, prefix_name=False)], verbose: bool = False): ...
tyro.cli(main)
```

- tyro reads the flags off the constructor's `__signature__`. It calls the constructor after parsing, and the constructor runs `_merge_from_flat` and `build()`. This works inside a subcommand's dataclass too, and the flags get their own help section named after the parameter.
- Each flag is `Annotated[Any, PrimitiveConstructorSpec(nargs=…), tyro.conf.arg(name=…, prefix_name=False)]`. `nargs` takes `1`, `"*"`, `N`, and `(1, N)`. The last one expresses `whole_value` natively.
- A value-less flag is `bool` with `tyro.conf.FlagCreatePairsOff`.
- These names register and parse: `db.host`, `xs+`, `xs.0-`, `d.a/b.k`, `d.a b.k`, `d.x[0].k`, `x.json`, `0.size`, `class`.
- tyro accepts a repeated one-token flag, a repeated `"*"` flag and a bare `--xs`, so `drop_bare_occurrences` is not needed.
- `-1`, `${...}`, `None` and `--x=` reach the constructor as raw strings.
- A `ConfargError` propagates out of `tyro.cli`.
- tyro binds `"*"` and `(1, N)` greedily, past `N` too, so the adapter passes `binds_runs=True`, as argparse and cyclopts do.
- tyro's argparse backend (`PYTHON_TYRO_BACKEND=argparse`) gives the same results. The one exception is argparse's `-1.5e3` refusal, which confarg's argparse adapter already shares.

## Open points for the design pass

1. **The API shape.** tyro has no app object to populate, so the register/merge/build triple collapses into one annotation, the way cyclopts' `merge_app` already absorbs the parse ([the quartet](../../architecture/cli-adapters/model.md#the-quartet)). It is open where `merge_*` (the raw dict) lives, and how `MergeOptions` reach the constructor.
2. **The argv handover.** `constructor_factory` runs inside `tyro.cli` but cannot see its `args=`, so it defaults to `sys.argv[1:]`. An explicit argv needs a confarg wrapper around `tyro.cli` or a context variable. The constraint is the one [limitations](../../architecture/limitations.md#cli-front-ends) already states for every adapter.
3. **`_` and `-` are one delimiter in tyro, always.**
   - tyro registers a name segment by segment but normalizes the typed token as one string. A segment that starts with `_` after a dot, or ends with `_` before one, is therefore registered and then refused: `--f._class`, `--f._call.x`, `--db._secret`, `--d.a_.b`. A plain nested dataclass with a field `_x` hits it too, on both backends. It is not a documented rule: tyro's #77/#78 made registration keep the underscore on purpose, and nothing tests typing such a flag. As of 2026-10-10 no tyro issue reports it. Registering `tyro._strings.swap_delimiters(name)` works around it (probed), but `--help` then spells `--f.-class`, and the function is private. An upstream fix is the clean route.
   - tyro accepts `--a-b` for a registered `--a_b`. Vanilla refuses `--a-b`, but `_require_argv_spells` would refuse it first with the misleading "not one command line" message. The adapter needs to check the spelling before tyro parses.
   - Two dict keys that differ only by `_` and `-`, both typed, crash tyro with `AssertionError: Name conflict`. The adapter has to dedupe by normalized name.
4. **Divergences to put to the maintainer** ([feature design](../../architecture/invariants.md#cross-channel-parity)):
   - tyro has no hide-but-accept flag, since `tyro.conf.Suppress` also removes the flag from parsing. The [hidden index spellings](../../architecture/design-decisions/index-spellings-are-hidden-from-help.md#index-spellings-are-hidden-from-help) would either show in `--help` or register only when argv types them.
   - Completion: `--tyro-write-completion` writes a static script, so dynamic flags and `FlagSpec.completer` never complete. The precedent is cyclopts, which has no completion ([completion](../../architecture/cli-adapters/completion.md)).
   - `FlagSpec.group` collapses into the parameter's section.
   - A `ValueError` raised in the constructor, for instance from a user's `__post_init__`, is caught by tyro and becomes exit 2, where the other adapters propagate it. tyro does this deliberately (#482, in 1.0.16).

## Not this design

tyro's documented route to config files is `tyro.cli(Cfg, default=loaded)`: confarg would load files and the environment, and tyro would own the CLI grammar (`--xs 1 2`, unions as `cfg:variant` subcommands, no patches, no `--config`). That breaks [cross-channel parity](../../architecture/invariants.md#cross-channel-parity), and that is why the field confarg owns uses confarg's grammar. A tyro user meets that boundary at the annotated parameter, and the docs have to say so.
