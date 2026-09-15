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
`cli._collect._merge_from_flat`, which is the whole shared tail: strip the prefix →
`_collect_ns_fields` → patch scan (`_collect_cli_patch_ops`) → `apply_root_json` →
`_collect_config_file_pairs(argv)` → `_pipeline._merge_sources`. `from_*` = `merge_*` +
`build()`. Only the flattening is per-adapter, so the three cannot drift. Keyword names and
order mirror `confarg.load` exactly. `populate_*` defaults `argv` to `sys.argv[1:]` like
`merge_*`, so the host parser accepts every flag `merge_*` will consume; `argv=[]` registers
only static flags.

Asymmetry: cyclopts is signature-driven and has no separate parse result to hand over, so
`merge_app`/`from_app` call `app.parse_args` themselves and `sys.exit` on `--help`/`--version`.

## The cli_prefix boundaries

`cli_prefix` ([03](03-cli-parsing.md#cli_prefix)) is a naming convention, not a parsing mode.
It is applied and removed at two boundaries, and nothing in between knows about it:

| Boundary | Direction | Function |
|---|---|---|
| `populate_*` | out | `_prefix.apply_prefix` renames every `FlagSpec` |
| `merge_*` | in | `_prefix.strip_flat_prefix` on the parse result, `_prefix.strip_argv_prefix` on argv |

That works because `FlagSpec.name` carries no `--` and each adapter builds its flag string at
exactly one site, while the flat parse result is keyed by that same dotted name. argv must be
stripped too, not parameterised: the patch and config scans resolve dotted paths against the
target type, which knows nothing of the prefix. The strippers are **lenient** where vanilla's
`_strip_cli_prefix` raises — a flag outside the prefix is the host's, not a typo — and they
drop a foreign flag together with its values, so the left-to-right order the scans depend on
survives.

A nameless `FlagSpec` is the scalar root: `apply_prefix` turns it into the bare `--<prefix>`
flag, and drops it when there is no prefix. `strip_flat_prefix` maps that key back to `""`,
which `_collect_ns_fields` reads as `__root__`.

`populate_*` records the prefix so `merge_*` can recover it, on whatever survives into the
merge step — which differs per framework, since none of the three hands the merge step the
object the flags were registered on: argparse gets only a Namespace, so it rides there via
`set_defaults`; click commands get their `params` copied onto other commands, so it rides on
the options; cyclopts hands back the App, so it lives in `_app_meta`. `resolve_prefix` is the
one place the recovered and the passed value are reconciled.

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

`_spec.py` (the model) and `_build.py` (spec generation) live in `cli/`, beside the other two
modules every adapter shares, `_prefix.py` and `_collect.py`; `cli/argparse/` holds only what
speaks argparse. They grew out of the argparse backend and sat under `cli/argparse/` until
REF-1 moved them. That was not only tidiness: while `confarg.cli` re-exported from
`confarg.cli.argparse._build`, importing the neutral model executed the argparse package's
`__init__`, so a click or cyclopts user paid for `_register.py`, `_namespace.py` and
`_completion.py` to be imported. `confarg.cli` is now the only export path for the four
neutral names (`FlagSpec`, `FieldMeta`, `build_static_flags`, `build_dynamic_flags`) and
`confarg.cli.argparse` deliberately does not alias them, so `import confarg.cli.click` leaves
`confarg.cli.argparse` out of `sys.modules` entirely. The rule that `_build.py` must not
import argparse predates the move and outlives it — it is what kept the module movable.

`_build.py` imports `_parse_cli` inside functions: importing it at module level would
create a load-time import cycle.

## Static and dynamic flags

**Static flags** come from a walk of the target type (`build_static_flags`): leaves, tuples,
namedtuples (whole, per name and per index), union tags and variant fields, plain callable
openers (`.fn`/`.class`/`.call`), `--config` and `--config.<struct field>`, and
`--config.<locals>` (the CLI way to declare locals). `build_static_flags` takes `argv` too, but
only to import the classes it names by `union_tag` before the walk starts; it never adds a flag
from it, so `argv=[]` still describes exactly the declared type.

**Dynamic flags** (`build_dynamic_flags`) are those whose existence depends on what the
user typed, found by scanning argv (and config files named on argv):

- bind/factory parameters of callables, whether the class is named by `--f.fn/.class/.call`,
  by a whole-value `--f '{"class": …}'` blob, or by a config file;
- escaped openers (`--f._class`) actually typed;
- `--config.<any.depth>[+]`;
- collection patches (`--f.N`, `--f+`, `--f.N-`, `--f.key`) and `.json` casts.

Why dynamic: the framework must accept every token the user types, but registering every
possible index, key or bind parameter statically is impossible, and registering rarely used
forms (escaped openers, `.json`) statically would clutter `--help`. Dynamic registration is
**best-effort**: any exception returns no extra flags rather than breaking `populate_*`; the
worst case is the framework rejecting a flag.

Best-effort, but not silent (BUG-5). A failure emits a `ConfargWarning` naming the original
exception: the rejection the user then sees comes from the host framework and says nothing
about the real cause, so without the warning a bug inside registration is indistinguishable
from a flag the user mistyped. Swallowing stays the default because the alternative — letting
the exception escape — takes down every `populate_*` call and shell completion over a flag
that may not even be typed; a caller who wants it fatal has
`warnings.filterwarnings("error", ConfargWarning)`, the hatch `exceptions.py` documents. The
warning fires from the one shared `build_dynamic_flags`, so all three adapters report
identically; vanilla `load()` registers nothing and has no analogue.

Escaped opener specs carry no group: sharing a group name with a different description
trips cyclopts' "2 distinct Group objects with same name" check.

## Whole-value flags

A bare `--<field> '{…}'` assigns an entire object in one token — the CLI peer of the env
channel's `PFX_ENV='{"a":"b"}'`. `_parse_cli._accepts_object_value` is the one predicate
deciding which field types take one: dataclass, namedtuple, dict, callable, or a union with any
of those as a variant. It answers for the vanilla parser, for static registration and for the
collector, so the three cannot drift.

The flags are **static**, not argv-scanned: the field is declared, so it belongs in `--help`
next to the bare `--tags` / `--pair` flags lists and tuples already get, and completion can
offer it. `nargs=None` — vanilla consumes exactly one token here, rejects a second as a stray
positional, and rejects none at all with `Missing value`
([10](10-design-decisions.md#a-whole-value-flag-needs-its-value)): the `FlagSpec` vocabulary
deliberately has no optional-value `"?"`, because cyclopts cannot express one. The metavar is `JSON` only where the predicate says the token is decoded, so a field that
keeps its token raw does not advertise a syntax it will not honour. Optionality is not one of
the things that decides this: `dict[str, str] | None` takes the mapping `dict[str, str]` takes,
`Callable[…] | None` takes the spec `Callable[…]` takes, and both get the same `JSON` metavar
([10-design-decisions.md#optionality-does-not-change-what-a-whole-value-accepts](10-design-decisions.md#optionality-does-not-change-what-a-whole-value-accepts)).
A decoded callable blob buys the factory and `bind` flags its class implies, exactly as a
`--<field>.class` opener does ([BUG-22](../todo/bugs.md), closed). Neither half of that is a
second decision: `_blob_document_from_argv` nests argv's `{`-prefixed tokens into one
config-file-shaped document and hands it to the *same* target walk that reads a `--config`
file's openers, and the flat collector's `active_directives` probe asks the blob's keys
alongside the flat flags, so a blob's `class` selects the directive form and opens the sibling
`--<field>.<param>` init kwargs the opener flag opens. Feeding the walk rather than
pattern-matching argv is what keeps a mapping field whose value happens to carry a `class` key
from being read as a callable spec — the walk is type-guided, the scan is not. Openers still
win over the blob they refine, matching the collector's deep merge. The string shorthand `--<field> some.module.fn` buys them too: it is the
spelling `{fn: …}` abbreviates, so the argv scan collects a bare string as a whole value
beside a `{`-prefixed blob and hands both to the same type-guided walk, which has always read
a config file's string spec that way. The collector then folds the string into the spec its
sibling flags built, under the plain `fn` the bare form implies — an opener flag beside it
still wins, being another spelling of the target rather than a refinement
([03](03-cli-parsing.md#token-consumption)). A *delete* flag is the exception, since it
travels with the patch ops rather than the flat collector ([BUG-24](../todo/bugs.md)).

A **fixed-arity** flag — a namedtuple or a `tuple[X, Y]` — is registered with the framework's
own exact token count, which is decided before argv is parsed and therefore cannot also admit
the single whole-value token vanilla takes (`--pair '[13, 42]'` for the tuple, `--pair
'{"x": 13}'` for the namedtuple). `FlagSpec.whole_value` marks those specs, and each adapter
grants what its framework can express (BUG-20, closed):

| Front-end | Registration | `--pair 13 42` | `--pair '[13, 42]'` |
|---|---|---|---|
| vanilla | — | ✅ | ✅ |
| argparse | `nargs="*"` | ✅ | ✅ |
| cyclopts | `consume_multiple=True` | ✅ | ✅ |
| click | `nargs=<n>` | ✅ | ❌ |

click is the exception, and it is an **approved divergence**
([09](09-invariants.md#cross-channel-parity)). A click `Option` cannot vary its token count:
`nargs=-1` raises `nargs=-1 is not supported for options`, and the only alternative,
`multiple=True`, would buy the whole-value token by taking `--pair 13 42` away and demanding
`--pair 13 --pair 42` in its place. Inline JSON is not what a CLI user reaches for, so click
keeps the readable positional form and declines the whole value, per
[10](10-design-decisions.md#a-divergence-leans-towards-the-affected-backends-own-idiom). The
divergence is confined to click: argparse and cyclopts, which *can* vary the count, get both.

Registering `nargs="*"` hands **arity enforcement back to confarg** — the framework no longer
counts the tokens, so `--pair 1 2 3` reaches `build()` and fails there rather than at the
parser. That is not new machinery: a union with a sequence variant (`str | tuple[str, str]`)
has registered `nargs="*"` and let `build()` judge the arity since it was first written, so a
fixed-arity flag now behaves the way the union-wrapped one already did. The error text differs
from vanilla's, which consumes exactly the declared count and reports the surplus token as
`Unexpected positional argument: '3'`; both are `ConfargError`, which is the level the contract
suite asserts.

For the namedtuple, `cli/_collect.py` decodes the lone token through
`_fixed_arity_whole_value`, which delegates to the same two decoders the other branches use
(`_json_array_override` for `[…]`, `_accepts_object_value` + `_parse_json_arg` for `{…}`), so
the object form cannot drift from what vanilla decodes. Sub-flags refine it exactly as they
refine a struct's whole value — by name over a decoded object, by position otherwise.

Everything else about a namedtuple is shared — the arity flag, the per-field and per-index
flags, and the vanilla positional form
([10](10-design-decisions.md#a-namedtuple-is-a-fixed-length-sequence)).

A dict field's bare flag is its *only* static flag (its keys are unknown until argv is read);
subkeys arrive as patch flags and are deep-merged over the whole value, so
`--env '{"a":"b"}' --env.c d` yields `{"a": "b", "c": "d"}` as in vanilla.

Limitation, shared with [collection patches](#collection-patch-parity): a framework's parse
result carries no argv order, so the adapters always let a sibling `--<field>.<sub>` refine
the whole value. Vanilla honors argv order, so `--sub.a 3 --sub '{"a":2}'` disagrees. The
useful order — whole value first, refinements after — agrees.

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
  completion paths). "Has subclasses" means *imported* subclasses, so the class a tag names on
  argv or in a `--config` file is imported first, by `_tags.import_tagged_classes`
  ([10](10-design-decisions.md#a-named-tag-is-imported-before-registration)); without that the
  selector and the subclass's own flags exist or not depending on which modules happened to
  load ([BUG-6](../todo/bugs.md), closed). The completer is left unset when the subclass list
  is empty — an empty one suppresses the shell's own suggestions.

  Registration and collection read the *same* answer: `merge_*` runs `_tags.collect_tags` over
  the stripped argv and hands the resulting `{field path: class path}` map to
  `_collect_ns_fields`, so the flat collector descends into the subclass a `--config` file names
  exactly as it descends into one a `--<path>.<union_tag>` flag names. Reading the tag from the
  flat parse result alone left a subclass field typed on the CLI with no type to hang on, and it
  was dropped while vanilla kept it ([BUG-19](../todo/bugs.md), closed). Only a tag found in
  *flat* is written back into the collected dict: a file's tag already reaches the merge at its
  own priority, and re-emitting it at CLI priority would replace the file's plain string with a
  `_StrToken` and break [byte-identical merged dicts](#byte-identical-merged-dicts).
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
