# CLI adapters (argparse, click, cyclopts)

## Why adapters exist

confarg parses argv itself; an application needs no CLI library. The adapters exist so
users can keep their favorite CLI library (help, completion, subcommands) while confarg
still owns configuration semantics. They are a translation layer, never a second
implementation: every adapter must produce exactly what `confarg.load()` would
([09](09-invariants.md#cross-channel-parity)).

## The triad

| | argparse | click | cyclopts |
|---|---|---|---|
| register flags | `populate_parser` (+ `make_parser`) | `populate_command` | `populate_app` |
| raw dict | `merge_namespace` | `merge_context` | `merge_app` |
| object | `from_namespace` | `from_context` | `from_app` |

`merge_*` → flatten the framework's result to `{dotted.flag: value}` →
`cli._collect._collect_ns_fields` → patch scan (`_collect_cli_patch_ops`) → `apply_root_json`
→ `_collect_config_file_pairs(argv)` → `_pipeline._merge_sources`. `from_*` = `merge_*` +
`build()`. Keyword names and order mirror `confarg.load` exactly, minus `cli_prefix`
([03](03-cli-parsing.md#cli_prefix)). `populate_*` defaults `argv` to `sys.argv[1:]` like
`merge_*`, so the host parser accepts every flag `merge_*` will consume; `argv=[]` registers
only static flags.

Asymmetry: cyclopts is signature-driven and has no separate parse result to hand over, so
`merge_app`/`from_app` call `app.parse_args` themselves and `sys.exit` on `--help`/`--version`.

## Only user-typed values

Framework defaults must never enter the CLI layer, or they would override config files and
env at the highest priority. Each framework needs its own mechanism:

- argparse: every argument uses `default=argparse.SUPPRESS`;
- click: `ctx.get_parameter_source(k) == ParameterSource.COMMANDLINE`;
  `allow_from_autoenv=False` so click never reads env itself (confarg does);
- cyclopts: every synthetic parameter defaults to `None`, and `None` values are dropped.

## Framework-neutral flag model

`FlagSpec` (name, `nargs`, choices, metavar, help, group, completer) is the contract between
spec generation and the adapters. `nargs`: `None` = one value, `"*"` = zero or more,
`int` = exact count, `0` = value-less switch (deletes). Each adapter re-expresses it
(argparse `nargs`/`store_true`; click `multiple=True`/`is_flag`; cyclopts
`consume_multiple`/`n_tokens`/`bool`).

`FieldMeta` (via `Annotated`) adds help and metavar without a custom field type. Help text
priority: `FieldMeta.help` > attribute docstring (read from source with `ast`; unavailable
for dynamically created classes) > empty.

`_build.py` must not import argparse. It (and `_spec.py`) lives under `cli/argparse/` for
historical reasons only — it grew out of the argparse backend. See
[REF-1](../todo/refactors.md).

`_build.py` imports `_parse_cli` inside functions: importing it at module level would
create a load-time import cycle.

## Static and dynamic flags

**Static flags** come from a walk of the target type (`build_static_flags`): leaves, tuples,
namedtuples (whole, per name and per index), union tags and variant fields, plain callable
openers (`.fn`/`.class`/`.call`), `--config` and `--config.<struct field>`, and
`--config.<locals>` (the CLI way to declare locals).

**Dynamic flags** (`build_dynamic_flags`) are those whose existence depends on what the
user typed, found by scanning argv (and config files named on argv):

- bind/factory parameters of callables named by `--f.fn/.class/.call` (in argv or config);
- escaped openers (`--f._class`) actually typed;
- `--config.<any.depth>[+]`;
- collection patches (`--f.N`, `--f+`, `--f.N-`, `--f.key`) and `.json` casts.

Why dynamic: the framework must accept every token the user types, but registering every
possible index, key or bind parameter statically is impossible, and registering rarely used
forms (escaped openers, `.json`) statically would clutter `--help`. Dynamic registration is
**best-effort**: any exception returns no extra flags rather than breaking `populate_*`; the
worst case is the framework rejecting a flag.

Escaped opener specs carry no group: sharing a group name with a different description
trips cyclopts' "2 distinct Group objects with same name" check.

## Collection patch parity

Frameworks own whole-field values (so click keeps its repeated-flag list syntax), but their
parse results cannot express argv-ordered, interleaved patches such as
`--dbs+ {} --dbs.-1.dbpath db1 --dbs+ {} --dbs.-1.dbpath db2`. The two halves:

1. `build_dynamic_flags` registers exactly the patch flags present in argv (value-less for
   deletes) so the framework accepts them;
2. `merge_*` re-runs the vanilla parse loop in `patch_only=True` mode over **argv** (not the
   framework result), which skips everything the flat collector owns and applies patch ops in
   command order, then deep-merges them over the collected values.

Argv (not the namespace) is also what preserves the left-to-right order of interleaved
`--config[.subpath]` flags. Both halves route the decision through
`_is_collection_patch_path` (so `--input.1.str yes`, a cast on an element, is a patch).

History: patches, dict subkeys, bind-on-`__call__` and expressions over CLI numbers were
vanilla-only until PR #72.

## Byte-identical merged dicts

Adapters must produce the same merged dict as vanilla, byte for byte (the contract suite
checks it). Therefore `_collect.py` mirrors vanilla decisions exactly: eager leaf coercion
through `_try_coerce`; single-element lists for scalar+sequence unions collapse to
`_UnionSeqToken`; a lone JSON-array token is decoded with vanilla's `_try_parse_json_list`
and stored raw; scalar casts via `_cast.resolve_forced_value`; callable specs keyed by the
active directive names from `_callable.active_directives`; root `--json` folded under
fields by `apply_root_json`. Without eager coercion, CLI numbers stayed strings and
`${base * 3}` failed (fixed in PR #99).

When no union tag is given, the collector collects the fields of **all** struct variants so
structural inference in `construct` can pick one.

## Expression-tolerant choice gates

Frameworks validate `Literal`/`Enum` choices at parse time, which would reject `${name}` on
the CLI while env and files accept it. Each adapter defers expression tokens via
`dictexpr.contains_expression` at the point where its framework validates, keeping native
help, completion and error text for real values:

| Framework | Bypass point | Why there |
|---|---|---|
| argparse | `_ExpressionTolerantChoices.__contains__` | argparse checks `value not in choices` and renders help by iterating the same object |
| click | `_ExpressionTolerantChoice.convert` | `Choice.convert` validates through a normalized mapping, not the container |
| cyclopts | `_expression_tolerant_convert` as `Parameter(converter=…)` | cyclopts enforces `Literal` by converting; the annotation stays for help |

`build()` validates the resolved value with the same `TypeCoercionError` everywhere.

## Union, inheritance and cast flags

- A struct union registers `--f.<union_tag>` plus the fields of every variant. Same-named
  flags from different variants are merged and their `choices` unioned
  (`_merge_or_append_spec`): first-wins would drop the other variants' values.
- A base class with subclasses registers the tag and all subclass fields (recursively for
  completion paths).
- Force-cast flags (`--f.int`, …) are registered statically only where the stealing rule is
  non-obvious: an enum variant, or `str` next to any other variant.

## Framework specifics

- **argparse**: value-less flags become `store_true` (argparse forbids `nargs=0` on store);
  argument groups from `FlagSpec.group`; `make_parser` defaults `allow_abbrev=False` so
  adding a field later cannot silently change what an abbreviated flag means.
- **click**: options cannot take `nargs=-1`, so `"*"` maps to `multiple=True` — hence the
  repeated-flag list syntax; no argument groups; `_ConfargOption` allows dotted names; the
  command callback is wrapped to strip confarg parameters from its kwargs.
- **cyclopts**: flags become a synthetic default function whose `inspect.Signature` holds one
  keyword-only parameter per flag; `_pyname` maps dotted names to unique identifiers and a
  name map restores them; metadata is kept in module-level `_app_meta` keyed by `id(app)`
  (App is unhashable) and holding a reference to the app so the id cannot be reused after GC;
  `negative=()` suppresses `--no-*`/`--empty-*`; there is no metavar, so the type name is
  prefixed to the help text. Cyclopts accepts both list syntaxes.

## Completion

Completion must never crash the shell; every failure degrades silently to fewer
suggestions.

- argparse (`argcomplete`): `setup_completion` pre-extends the parser with the fields of
  union classes already determinable from `--config` files or `--f.class` on the partial
  command line, and with callable bind flags. Cheap no-op outside completion mode.
- click: `setup_completion` reads `COMP_WORDS`/`COMP_CWORD` (bash, zsh) and adds dynamic
  flags. Fish is not supported yet.
- cyclopts: no confarg completion support.

## List syntax divergence

List values are space-separated for vanilla/argparse (`--tags a b`), repeated flags for click
(`--tags a --tags b`), either for cyclopts. This is an approved divergence imposed by
click; tests keep it visible ([12](12-testing.md#list-syntax-split)). The append/delete
ordering on top is shared.
