# CLI adapters (argparse, click, typer, cyclopts)

## Why adapters exist

confarg parses argv itself; an application needs no CLI library. The adapters exist so
users can keep their favorite CLI library (help, completion, subcommands) while confarg
still owns configuration semantics. They are a translation layer, never a second
implementation: every adapter must produce exactly what `confarg.load()` would
([09](09-invariants.md#cross-channel-parity)).

## The quartet

| | argparse | click | typer | cyclopts |
|---|---|---|---|---|
| register flags | `populate_parser` (+ `make_parser`) | `populate_command` | `populate_command` | `populate_app` |
| raw dict | `merge_namespace` | `merge_context` | `merge_context` | `merge_app` |
| object | `from_namespace` | `from_context` | `from_context` | `from_app` |

`merge_*` → flatten the framework's result to `{dotted.flag: value}` →
`cli._collect._merge_from_flat`, which is the whole shared tail: strip the prefix →
`_collect_ns_fields` → patch scan (`_collect_cli_patch_ops`) → `apply_root_json` →
`_collect_config_file_pairs(argv)` → `_pipeline._merge_sources`. `from_*` = `merge_*` +
`build()`. Only the flattening is per-adapter, so the four cannot drift. Keyword names and
order mirror `confarg.load` exactly. `populate_*` defaults `argv` to `sys.argv[1:]` like
`merge_*`, so the host parser accepts every flag `merge_*` will consume; `argv=[]` registers
only static flags.

Asymmetry: cyclopts is signature-driven and has no separate parse result to hand over, so
`merge_app`/`from_app` call `app.parse_args` themselves and `sys.exit` on `--help`/`--version`.
Typer is signature-driven too, but it compiles the signature down to a command object, so
`populate_command` takes what `typer.main.get_command(app)` returns and the pair is click's.

## The clicklike seam

Typer was once a layer over click, which is why the typer examples were written against
`confarg.cli.click` and why no typer adapter existed. It now **vendors click**
(`typer/_click/__init__.py`: *"Code taken and adapted from Click 8.3.1"*; verified against
typer 0.27.2, which is the floor — the release that introduced the fork was not checked), so
`typer._click.Context`, `.Parameter` and `.Command`, `typer.core.TyperOption` and
`typer._types.TyperChoice` are now unrelated to the real click classes of the same shape.
Registering a real `click.Option` on a typer command therefore fails inside click's own
`Parameter.handle_parse_result`, which reaches for a `Context` slot typer's fork does not have
(BUG-7); and `Context.get_parameter_source` returns a member of *typer's* `ParameterSource`,
which is never equal to a member of click's. Neither break is in the merge path.

Typer is consequently a front-end in its own right, not a click spelling — but the two
frameworks' APIs still match almost everywhere, so `cli/_clicklike/` holds every part that
does not name a framework class and each adapter supplies only what its framework spells
differently:

| Shared in `_clicklike` | Supplied by the adapter |
|---|---|
| `option_kwargs` — the whole `FlagSpec` → option-keyword mapping | the choice class, the completion keyword |
| `DottedNameMixin` — `--db.host` is not an identifier | the option base class |
| `ExpressionTolerantChoiceMixin` — the `${...}` bypass | the choice base class |
| `StandsBareMixin` — a flag that may carry no value ([below](#a-flag-that-stands-bare)) | the option base class |
| `load_flags_into_command`, `populate_command` | the option factory and class |
| `flat_from_ctx`, `registered_prefix`, `merge_from_ctx`, `construct_from_ctx` | nothing — the Context is duck-typed |
| `setup_completion`, `partial_argv_from_env` | the option factory |

These are supplied as **mixins placed ahead of the framework's own class**, not as a wrapper
around it: each framework must keep its real base (typer inspects `TyperOption` to render help
and to wire completion), so what is shared is the behavior, not the hierarchy.

`flat_from_ctx` compares the parameter source **by member name** (`"COMMANDLINE"`) rather than
by identity. That is the one place the fork is visible in shared code, and the alternative —
passing each framework's enum in — buys nothing: the question "did the user type this?" has one
answer, and the name is what both forks agree on.

`_clicklike` imports neither click nor typer, so `import confarg.cli.typer` leaves click out of
`sys.modules` and vice versa — the same property REF-1 bought for `cli/_build.py` against
argparse ([below](#framework-neutral-flag-model)).

Where the frameworks genuinely disagree, the seam widens rather than the shared code branching.
Completion is the only such case so far: click takes a `shell_complete` callback returning its
own `CompletionItem`s, while typer deprecates that in favour of an `autocompletion` callback
returning bare strings which typer wraps itself. So `option_kwargs` takes a
`completer_kwargs` builder instead of a completion-item class. Typer additionally filters the
result by `startswith(incomplete)`, which changes nothing: a confarg completer
(`_build._make_path_completer`) already prefix-filters.

The adapter reaches into two private typer modules (`typer._types`, `typer._click`), because
`TyperChoice` and the fork's `Context`/`Command` types have no public spelling. The exposure is
confined to `cli/typer/_register.py`'s imports, and `cli/typer/__init__.py` probes those names
in its availability guard so a typer too old to vendor click reports confarg's own message
rather than an ImportError on a private module. `typer>=0.27` is therefore the floor.

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
merge step — which differs per framework, since none of the four hands the merge step the
object the flags were registered on: argparse gets only a Namespace, so it rides there via
`set_defaults`; click and typer commands get their `params` copied onto other commands, so it
rides on the options; cyclopts hands back the App, so it lives in `_app_meta`. `resolve_prefix` is the
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
`consume_multiple`/`n_tokens`/`bool`). Two flags qualify what `nargs` alone cannot say:
`whole_value` ([below](#whole-value-flags)) and `stands_bare` ([below](#a-flag-that-stands-bare)), each
honored by the adapters whose framework can.

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
openers (`.fn`/`.class`/`.call`), `--config` and `--config.<mount point>` (a struct field, or
a dict field — where a fragment of unknown keys belongs; a union of structs is still skipped,
BUG-70), and
`--config.<locals>` (the CLI way to declare locals). `build_static_flags` takes `argv` too, but
only to import the classes it names by `union_tag` before the walk starts; it never adds a flag
from it, so `argv=[]` still describes exactly the declared type.

**Dynamic flags** (`build_dynamic_flags`) are those whose existence depends on what the
user typed, found by scanning argv (and config files named on argv):

- bind/factory parameters of callables, whether the class is named by `--f.fn/.class/.call`,
  by a whole-value `--f '{"class": …}'` blob, or by a config file;
- escaped openers (`--f._class`) actually typed;
- bind subkeys typed in argv in either spelling (`--f.bind.p`, `--f._bind.p`), including the
  one the opener left inactive, whose keys are ordinary data and so describe no signature
  ([06](06-callables.md#plain-and-escaped-directives));
- `--config.<any.depth>[+]`;
- collection patches (`--f.N`, `--f+`, `--f.N-`, `--f.key`) and `.json` casts;
- the flat tagged-leaf flags typed below a registered leaf field (`--id.class`,
  `--id.hex`, BUG-56) — registered only when typed, on the same help-noise ground as the
  escaped openers: a registered leaf's ordinary spelling is its scalar, and one flag per
  `__init__` parameter would clutter `--help` for the escape hatch.

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
warning fires from the one shared `build_dynamic_flags`, so all four adapters report
identically; vanilla `load()` registers nothing and has no analogue.

Escaped opener specs carry no group: sharing a group name with a different description
trips cyclopts' "2 distinct Group objects with same name" check.

Everything below a callable field is the one family registered from the **path** rather than
from a signature (BUG-25, BUG-28). `_parse_cli._addresses_callable_key` is the shared
predicate, so whatever the vanilla parser accepts below the field the host framework accepts
too. A signature cannot answer here at all: not for a bind subkey in the spelling the opener
left inactive, whose keys are data ([06](06-callables.md#plain-and-escaped-directives)); not
for a sibling kwarg the named target does not carry; and not for a field with no opener
anywhere, which names no target to inspect. Letting the framework reject those first is what
made the five front-ends disagree — the flag is the adapter's to accept and the kwarg is
construction's to judge, so the user hears the real complaint (`Unknown kwargs [...]`,
`must specify one of 'fn', 'class', or 'call'`) instead of `unrecognized arguments`.

One predicate for the whole subtree needs the *collector* to read the whole subtree, which is
the other half of BUG-28: `_collect_callable_spec` used to gather sibling `--<field>.<param>`
flags only when an opener was present, so registering them alone would have dropped their
values silently instead. It now gathers them unconditionally, as the vanilla parser has always
written them — the opener decides what a key *means*, never whether it is stored.

The predicate answers about a *path*, so the caller strips an append/delete suffix before
asking. Those flags belong to the patch scan, which registers each in the shape its mode
demands; claiming `--f.bind.<key>-` here registered a value-less delete as if it took an
argument (BUG-29).

## Whole-value flags

A bare `--<field> '{…}'` assigns an entire object in one token — the CLI peer of the env
channel's `PFX_ENV='{"a":"b"}'`. `_parse_cli._accepts_object_value` is the one predicate
deciding which field types take one: struct (dataclass *or* plain class), namedtuple, dict,
callable, or a union with any of those as a variant. It answers for the vanilla parser, for
static registration, for the collector and for the env channel's `{`-led value, so the five
cannot drift. A plain class counts because the blob is taken apart into fields and
construction takes both spellings of a struct apart the same way; env and files accepted it
while the CLI alone refused until BUG-39 deleted the env channel's second answer.

The struct arm asks `_is_struct`, **not** the narrower
`typedload._coerce._is_struct_variant` that construction's dispatchers ask
([05](05-types-and-construction.md#leaf-coercion)). The two disagree on a registered leaf
with an `__init__` — `UUID`, say — and this question comes first: an explicit tag naming
such a class still builds it from its fields
([10](10-design-decisions.md#an-explicit-tag-opts-a-leaf-back-in)), and the tag cannot be
seen until the token is decoded. Refusing the token here would put that hatch out of the
CLI's reach while leaving it open to env and files, and would silently coerce the JSON
*text* into a leaf instead. `cli/_collect.py` therefore honors the decoded whole value in
its registered-leaf branch before falling back to scalar coercion, the order vanilla's
`_consume_value` already has. The `--help` metavar stays `VALUE` there: the rule is that
`JSON` implies the token is decoded, not the converse, and a registered leaf's ordinary
spelling is its scalar, with the tagged blob an escape hatch rather than the syntax to
advertise.

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
The hatch's *flat* spelling crossed the same seam one step later (BUG-56):
`--id.class uuid.UUID --id.hex …` is what the environment says with `ID__CLASS` /
`ID__HEX`, and vanilla accepted it all along because its type walk treats a registered
leaf structurally — the tag segment resolves through the `union_tag` rule, a parameter
through the leaf's `__init__` fields. The adapters now mirror that walk from both sides:
registration is argv-scanned
([above](#static-and-dynamic-flags)), accepting exactly what
`_parse_cli._resolve_field_type` accepts — so `--id.bogus` stays unregistered and the
framework's rejection stands in for vanilla's `no_such_field` — and the collector descends
into the leaf as it descends into a struct, writing the tag back raw, before the import
resolves, for the [BUG-45](#union-inheritance-and-cast-flags) reason. A registered leaf
as the *root* target keeps the gap (BUG-71).

A decoded callable blob buys the factory and `bind` flags its class implies, exactly as a
`--<field>.class` opener does. Neither half of that is a
second decision: `_blob_document_from_argv` nests argv's `{`-prefixed tokens into one
config-file-shaped document and hands it to the *same* target walk that reads a `--config`
file's openers, and the flat collector's `active_directives` probe asks the blob's keys
alongside the flat flags, so a blob's `class` selects the directive form and opens the sibling
`--<field>.<param>` init kwargs the opener flag opens. Feeding the walk rather than
pattern-matching argv is what keeps a mapping field whose value happens to carry a `class` key
from being read as a callable spec — the walk is type-guided. The opener scan
(`_collect_fn_paths_from_argv`) pattern-matches the `.fn`/`.class`/`.call` suffix too,
so a struct field literally named like an opener would be misread as an opener for its
parent; it now asks the same type-guided question — does the path resolve to a
callable-typed field? — before accepting the match, so a plain struct field named `fn`
(or `class`/`call`) is a value, not an opener (BUG-30). Openers still
win over the blob they refine, matching the collector's deep merge. The string shorthand `--<field> some.module.fn` buys them too: it is the
spelling `{fn: …}` abbreviates, so the argv scan collects a bare string as a whole value
beside a `{`-prefixed blob and hands both to the same type-guided walk, which has always read
a config file's string spec that way. The collector then folds the string into the spec its
sibling flags built, under the plain `fn` the bare form implies — an opener flag beside it
still wins, being another spelling of the target rather than a refinement
([03](03-cli-parsing.md#token-consumption)). A *delete* flag refines it too, even though it
travels with the patch ops rather than the flat collector: the patch scan is handed the
collected dict and opens the shorthand there as well
([below](#a-patch-op-joins-the-values-the-framework-collected), BUG-24).

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
| typer | `nargs=<n>` | ✅ | ❌ |

click and typer are the exception, and it is an **approved divergence**
([09](09-invariants.md#cross-channel-parity)). A click `Option` cannot vary its token count:
`nargs=-1` raises `nargs=-1 is not supported for options`, and the only alternative,
`multiple=True`, would buy the whole-value token by taking `--pair 13 42` away and demanding
`--pair 13 --pair 42` in its place. Inline JSON is not what a CLI user reaches for, so click
keeps the readable positional form and declines the whole value, per
[10](10-design-decisions.md#a-divergence-leans-towards-the-affected-backends-own-idiom). The
divergence is confined to the two clicklike front-ends — typer inherits it along with the
option class it forked ([above](#the-clicklike-seam)); argparse and cyclopts, which *can* vary
the count, get both.

Registering `nargs="*"` hands **arity enforcement back to confarg** — the framework no longer
counts the tokens, so whatever argv held arrives in one list and the count is the collector's
to check. The two bounds are not the same job, and only one of them can be answered here.

What a *repeat* of the flag means is the other half of the greedy registration, and the two
frameworks that vary the count answer it in their own idiom. Argparse's plain store keeps
only the last occurrence by construction. Cyclopts' `consume_multiple=True` accumulates the
token runs of every occurrence into one list — a list that never existed in argv and whose
seams the collector cannot recover — so the same setting cannot serve both jobs: it is what
a varlen list wants (`FlagSpec.accumulates`, [below](#list-syntax-divergence)) and what a
fixed-arity flag must not keep. A whole-value spec therefore registers a converter
(`cli/cyclopts/_register._last_occurrence_convert`) that keeps only the last occurrence's
run, read off the `CliToken.index` restart that survives into the converter, so `--pair 1 2
--pair 3 4` is `(3, 4)` on cyclopts as on every other front-end (BUG-62, closed).

Both are parse-time facts, so `cli/_collect._require_fixed_arity` answers both, mirroring the
`_require_value` vanilla asks once per positional token
([03](03-cli-parsing.md#token-consumption)). It is asked of the field type **as resolved,
without unwrapping `Optional`** — the type vanilla dispatches on: `tuple[X, Y] | None` is a
union with a sequence variant there, consumes greedily, and owes neither bound, so unwrapping
first would make the adapters refuse `--pair 1` where vanilla accepts it.

The **lower** bound: a short token run is `Missing value for '--pair'` and not a shorter tuple,
because a fixed arity is not one of the shapes a bare flag is reserved for
([10](10-design-decisions.md#a-whole-value-flag-needs-its-value)). The **upper** bound: a token
past the run is `Unexpected positional argument: '3'` and not a longer tuple, because vanilla
stops consuming at the declared count and meets the next token in its argv scan as a stray
positional. The two errors have one owner each — `ConfargError.missing_value` and
`UnknownArgumentError.unexpected_positional` — so the adapters raise what the vanilla scan
raises rather than a lookalike (BUG-58, BUG-60).

What sets the run's length is `_fixed_arity_whole_value`, asked of the **first token alone**: a
whole value is one token whatever arity it spells, a positional run is the full arity. That one
question settles both ends at once. `--pair '[13]'` is a complete run, so it stays the arity
error `build()` owns rather than becoming a flag left without a value; the `9` in
`--pair '[13]' 9` is past a run that already ended, so it is surplus rather than the token that
completes the pair. Click and typer register the exact count and enforce both bounds in their
own parsers, so the guard is dead weight there and live for argparse and cyclopts.

The guard is deliberately *not* extended to a union with a sequence variant (`str | tuple[str,
str]`): that field consumes greedily in vanilla too, so `build()` judging its arity is parity,
not a gap.

For the namedtuple, `cli/_collect.py` decodes the lone token through
`_fixed_arity_whole_value`, which delegates to the same two decoders the other branches use
(`_json_array_override` for `[…]`, `_accepts_object_value` + `_parse_json_arg` for `{…}`), so
the object form cannot drift from what vanilla decodes. Sub-flags refine it exactly as they
refine a struct's whole value — by name over a decoded object, by position otherwise — and
their values are coerced to their field's type as vanilla's own dispatch coerces them, so a
sub-flag feeds an expression the number it spelled and not its text (BUG-66).

The *order* the two halves arrived in is read back off argv, where a framework's parse
result cannot carry it: the arity flag is the latest writer exactly when its last
occurrence follows the last sub-flag's (`cli/_collect._arity_flag_writes_last`, the
read-back the patch and `--config` scans already perform), and then it overwrites the
field wholesale — `--pair.y 7 --pair 13 42` is `[13, 42]`, the sub-flag gone, while the
reverse order joins the two halves by field name. Latest arguments overwrite earlier
ones ([10](10-design-decisions.md#a-namedtuples-arity-flag-and-its-sub-flags-merge-in-argv-order)).

Everything else about a namedtuple is shared — the arity flag, the per-field and per-index
flags, and the vanilla positional form
([10](10-design-decisions.md#a-namedtuple-is-a-fixed-length-sequence)).

A dict field's bare flag is its *only* static flag (its keys are unknown until argv is read);
subkeys arrive as patch flags and are deep-merged over the whole value, so
`--env '{"a":"b"}' --env.c d` yields `{"a": "b", "c": "d"}` as in vanilla.

Limitation, shared with [collection patches](#collection-patch-parity): a framework's parse
result carries no argv order, and only the namedtuple's arity flag reads the order back off
argv (above). A struct or dict whole value is always refined by its sibling
`--<field>.<sub>` flags, so `--sub.a 3 --sub '{"a":2}'` disagrees with vanilla, which honors
argv order. The useful order — whole value first, refinements after — agrees.

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

### A flag that stands bare

Some flags are legal with nothing after them. `--<list>+` appends no items and leaves whatever
the lower-priority sources put in the list (`_parse_cli._handle_append_token`, which consumes
tokens until the next flag and is content with none). A varlen collection's own `--<list>` takes
zero tokens too and *clears* the collection, as does a union with a sequence variant — the two
multi-token branches of `_consume_collection_or_scalar`, named together in
`_build._takes_multi_tokens`. What they share is that vanilla consumes greedily there and asks
for nothing, so "zero or more" belongs to the multi-token *shape* rather than to what `"*"` means
everywhere: `--config` and `--config.<path>+` carry the same `nargs="*"` and still report
`Missing value` when vanilla finds no token.

The config flags stay outside the family on every front-end (BUG-51). A bare field flag has a
job of its own — a bare `--users` *clears* the list — while a bare `--config.<path>+` would mount
nothing and reset nothing, so the bare form spells nothing worth accepting, and refusing it is
what vanilla always did. The adapters' re-scan (`_parse_cli._collect_config_file_pairs`) raises
vanilla's message now, built by the one `_missing_config_path_msg` both scans share, so
argparse's `nargs="*"` — which takes zero tokens — and cyclopts' implicit empty container no
longer swallow the occurrence; cyclopts validates before its own parse, where an implicit token
meeting a real one trips a framework assertion. click and typer refuse the bare form in their own
parser, with the framework's "requires an argument", as they refuse the whole-value flags.

The same re-scan runs vanilla's subpath check too (`_parse_cli._check_mount_subpath`): a
`--config.<subpath>` naming no node of the target is refused on every front-end at parse time
(BUG-50, closed), not mounted silently to surface later as an unknown-field error from
`build()`.

A subkey or element flag (`--f.key`, `--f.N`) has whatever shape the type it addresses has, so it
answers the same predicate: `--map.k` on a `dict[str, list[int]]` and `--grid.0` on a
`list[list[int]]` stand bare and store the empty collection, while the same flags over a scalar
value type take exactly one token. Asking the predicate rather than the syntax is what keeps that
half in: click and typer refused those two spellings while the other three front-ends took them,
the same gap the field flag had (BUG-38).

Neither clicklike framework can express a flag that takes zero *or* more tokens: click and
typer fix an option's token count when the option is built, and the `multiple=True` the
adapters map `"*"` to always demands one. So a bare `--input+` was rejected with `Option
'--input+' requires an argument.` on both, while vanilla, argparse and cyclopts accepted it
(BUG-33), and a bare `--input` was rejected the same way (BUG-38). cyclopts reads a bare
occurrence as an implicit empty container and needs no help with it alone — but asserts
(`argument/_argument.py`, "implicit value, yet more than one token") the moment that implicit
token meets a real one, and rejects a second bare occurrence as a repeat.

So the spec keeps the multi-token shape and says, in `FlagSpec.stands_bare`, that the flag is
*also* legal with nothing after it; **the framework is handed an argv without the bare
occurrences** (`cli._argv.drop_bare_occurrences`). So the no-op is honored rather than rejected,
one argv may spell the same append both ways (`--users+ billy --users+`), and every front-end
answers alike (BUG-35).

Dropping a token is only safe where nothing is lost, and that is where the families differ:

- A bare **append**, and a bare **subkey or element flag**, are read back by the patch scan,
  which reads the argv the user typed rather than the framework's parse result. What a framework
  collected for them is discarded anyway — `_collect_ns_fields` walks the target type, where
  `users+`, `map.k` and `grid.0` name no field — so the drop costs nothing.
- A bare **field flag** is different: the empty value it stores is the *field's own*, so the flat
  collector owns it and the patch scan never sees it. Dropping the token alone lost the clear on
  all three filtered front-ends. It is read back in the merge step instead, from the same argv:
  `_collect._bare_multi_token_flags` names the bare-only flags whose type takes many tokens, and
  `_merge_from_flat` puts an empty value under each, leaving the collector branches to shape it
  exactly as they shape argparse's. With `setdefault`, so an occurrence that did carry items
  keeps what the framework collected (`--users x --users`, and `--users=--a --users` too, where
  the `=` token names `users=--a` rather than `users`).

One marker, two readers: `drop_bare_occurrences` decides which tokens a framework parses and
`bare_only_flag_names` decides what a dropped token meant, both off one `_bare_occurrence`
predicate so they cannot disagree about which occurrences are bare.

`_takes_multi_tokens` is the whole gate, asked once where the specs are built and again on the
merge side, so registration and read-back cannot disagree about which flags stand bare. It is the
multi-token *shape* and not "is there something to clear": a union with a sequence variant but no
varlen one (`str | tuple[str, str]`) is therefore included, and the empty value it stores is what
raises vanilla's error in `_collect_union_seq_value` — so the bare form is refused with confarg's
own message everywhere instead of the framework's. `stands_bare` is set on what that predicate
names plus the append; marking anything else needs a reader for what the dropped token meant, or
the information is gone.

It is one rule with one decision-maker and two application points, because the seam at which a
framework receives argv differs — as it does for
[`cli_prefix`](03-cli-parsing.md#cli_prefix), recorded per framework on whatever survives into
the merge step. cyclopts hands confarg the parse itself, so `merge_app` filters the tokens it
passes to `App.parse_args`. In click and typer the *host* calls the command, so the hook rides
on the options (`_clicklike.StandsBareMixin`): `add_to_parser` arms a filter on the parser
instance, which both frameworks build fresh per parse. A hook on the command would not survive
the `params` copying that groups and decorators do routinely. argparse and vanilla are exempt:
`nargs="*"` already takes zero tokens and accepts a second occurrence, so they parse the argv as
typed — which is the other reason the merge-side read-back is a `setdefault` over what argparse
already collected rather than an override of it.

"Carries an item" is asked with `_parse_cli._looks_like_flag`, the same value/flag split vanilla
consumes by, so the frameworks take exactly the tokens vanilla takes. That matters for
dash-prefixed items in particular: `--input+ -8` carries an item by vanilla's reckoning and is
kept, and `--input+=--a` carries its item by construction — a `=` token never matches a bare
occurrence.

Only a flag whose spec sets `stands_bare` is filtered, which is why the rule is a marker rather
than a syntax rule about trailing `+`: vanilla *rejects* a bare `--config.<path>+`
(`Missing file path after --config`), so the config-file append flags must not inherit it. The
scalar root flag clears the marker along with the rest of the multi-token shape, since
`_handle_scalar_root` consumes exactly one token whatever the root type is
([03](03-cli-parsing.md#cli_prefix)).

Rejected: click's own optional-value spelling (`is_flag=False` plus a `flag_value`). It fits
click alone — typer's vendored parser dropped the feature, so typer would have stayed red —
and it changes how click reads the token *after* the flag, treating anything beginning with
`-` as an omitted value. That breaks `--tags+=--a` and `--input+ -8`, which the dashed-value
escape requires
([10](10-design-decisions.md#the--form-is-the-escape-for-a-dashed-value),
`TestDashPrefixedValueContract`).

Also rejected: letting the spec shape follow argv — registering a value-less `nargs=0` when no
occurrence carries an item (how BUG-33 was first fixed). It answers the same question the
filter answers, and only for the homogeneous half of it, so the mixed argv stayed broken and
the two rules would have had to agree forever.

Also rejected for the collection flag: putting the empty value into the flat dict for *every*
bare occurrence, with no field-type gate. It needs no type walk, but it would quietly accept the
bare forms vanilla refuses — `--db` on a struct field, `--map` on a dict — wherever a framework
happened not to reject them first.

### A patch op joins the values the framework collected

Splitting one channel across two dicts costs what vanilla gets for free by writing both into
a single `ctx.data`: each half has to be told about the other, or the merge that rejoins them
reads them as two priorities rather than one. Two things follow, both settled by BUG-24.

**The patch scan is handed the collected dict** (`_parse_cli(..., patch_base=…)`). Vanilla
opens a bare-string callable shorthand before it stores a flag below it, through the one
`_open_callable_shorthand` every channel calls
([06](06-callables.md#cli)); in `patch_only` mode the scan's own dict is empty, because
`--fn pkg.func` belongs to the flat collector, so the opener saw nothing and the deep merge
replaced the scalar instead of refining it. Passing the collected dict in puts the shorthand
where the canonical opener can see it, at the same point in the same loop — rather than
teaching `cli/_collect.py` a second answer to a question `_parse_cli` already answers.

**A delete is re-asserted after the merge** (`_collect._restore_patch_deletes`). Inside one
channel `--<field>.<key>-` is a *record*, not an operation: vanilla stores the sentinel and
leaves `_merge_sources` to apply it against the lower-priority sources. `_deep_merge` applies
it on sight, which is right for its usual job of joining two priorities and wrong here, so
the sentinels the patch scan recorded are written back over the merged dict. Without that,
`--fn.fn X --fn.bind-` silently kept a config file's `bind` that vanilla deletes. Only
dict-key deletes carry a sentinel; a list index delete travels as an index list under
`"-"`/`"~"` and *is* an operation the merge applies, exactly as vanilla applies it.

Re-asserting means the delete wins wherever both spellings touch one key, which is the
[argv-order convention](#whole-value-flags) the adapters already follow — whole value first,
refinements after.

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
  load. The completer is left unset when the subclass list
  is empty — an empty one suppresses the shell's own suggestions.

  Registration and collection read the *same* answer: `merge_*` runs `_tags.collect_tags` over
  the stripped argv and hands the resulting `{field path: class path}` map to
  `_collect_ns_fields`, so the flat collector descends into the subclass a `--config` file names
  exactly as it descends into one a `--<path>.<union_tag>` flag names. Reading the tag from the
  flat parse result alone left a subclass field typed on the CLI with no type to hang on, and it
  was dropped while vanilla kept it. Only a tag found in
  *flat* is written back into the collected dict: a file's tag already reaches the merge at its
  own priority, and re-emitting it at CLI priority would replace the file's plain string with a
  `_StrToken` and break [byte-identical merged dicts](#byte-identical-merged-dicts).
  The write-back happens *before* the tag's import resolves, and through one shared step —
  `_collect._collect_named_variant` resolving with `_collect._tag_named_struct` — for the
  union-field and the inheritance branch alike; the argparse completion pre-extend resolves its
  tags through the same `_tag_named_struct`. Writing the tag only after a successful import (the
  inheritance branch's old shape) dropped a tag whose import failed, while vanilla keeps
  `--<path>.<union_tag>` as a raw string and lets `construct()` raise the import error naming the
  bad path — so the tag must survive collection byte-identically, or the user hears a
  "no discriminator was provided" complaint about a discriminator they did provide (BUG-45).
- Force-cast flags (`--f.int`, …) are registered statically only where the stealing rule is
  non-obvious: an enum variant, or `str` next to any other variant.

## Framework specifics

- **argparse**: value-less flags become `store_true` (argparse forbids `nargs=0` on store);
  argument groups from `FlagSpec.group`; `make_parser` defaults `allow_abbrev=False` so
  adding a field later cannot silently change what an abbreviated flag means.
- **click**: options cannot take `nargs=-1`, so `"*"` maps to `multiple=True` — hence the
  repeated-flag list syntax; no argument groups; `_ConfargOption` allows dotted names; the
  command callback is wrapped to strip confarg parameters from its kwargs.
- **typer**: everything click's entry says, since the option class is a fork of click's —
  `multiple=True` for `"*"`, no argument groups, dotted names via the shared mixin. What
  differs: `autocompletion` rather than the deprecated `shell_complete`, and
  `populate_command` takes the command `typer.main.get_command(app)` returns, not the
  `typer.Typer` app ([above](#the-clicklike-seam)).
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
- typer: the same shared hook, wired through typer's `autocompletion` keyword
  ([above](#the-clicklike-seam)).
- cyclopts: no confarg completion support.

## List syntax divergence

List values are space-separated for vanilla/argparse (`--tags a b`), repeated flags for click
and typer (`--tags a --tags b`), either for cyclopts. This is an approved divergence imposed by
click and inherited by typer's fork of it; tests keep it visible
([12](12-testing.md#list-syntax-split)). The append/delete
ordering on top is shared.

What the approval covers is the **spelling** — which of the two forms a framework accepts — and
not what a repeated flag *means*. The two once came apart unnoticed: `--tags a --tags b` built
`['a', 'b']` under click, typer and cyclopts and `['b']` under vanilla and argparse, with no
diagnostic either way, so the repeated line the click and typer tutorials teach lost every value
but the last when it was pasted into a vanilla app. That was an unapproved gap rather than a second
divergence, and it resolved towards **accumulation** (BUG-37): last-wins is unreachable for the
clicklike front-ends — repetition being their only multi-token spelling, taking just the final
occurrence would leave a click user no way to write `['a', 'b']` at all. So `--f x --f y` is a
second spelling of `--f x y` in all five front-ends, and mixing the two spellings adds up
(`--f x y --f z` → `['x', 'y', 'z']` wherever both are accepted).

The rule holds for the multi-token **field** flags: a varlen collection, and a union with a
sequence variant (`int | list[int]`, `str | tuple[str, str]` — the clicklike front-ends already
accumulated on both). It stops at a fixed-arity flag (`tuple[X, Y]`, namedtuple), which takes one
value and is last-wins on repetition everywhere
([10](10-design-decisions.md#a-namedtuple-is-a-fixed-length-sequence)), and it is not the `+`
suffix, which is a merge operator rather than a spelling (below).

Two consequences follow from the accumulation being over **tokens**, not over shaped values:

- vanilla joins the occurrences and shapes the result once, in `_parse_cli._varlen_value` /
  `_union_seq_value`. A whole-value inline JSON array is therefore a *single-token* spelling
  (`_lone_json_array`): `--tags '["a","b"]'` decodes, while `--tags '["a","b"]' --tags '["c"]'`
  and `--tags '["a","b"]' z` are two ordinary items. The adapters were already answering it that
  way, since `_collect._json_array_override` is handed everything a framework collected for the
  flag and asks the same "is it alone?" question of that whole list.
- argparse keeps only the last occurrence under a plain store, so a spec that accumulates asks for
  `action="extend"` (`FlagSpec.accumulates`, set on those two field families alone —
  `nargs="*"` is shared by seven flag families here and says nothing about repetition).
  `default=argparse.SUPPRESS` survives it: a flag nobody typed stays off the Namespace, and a
  first occurrence with no token still yields `[]`. click and typer accumulate already through
  `multiple=True`, cyclopts through `consume_multiple`.

Neither axis is the `+` suffix, which names the merge axis instead and is shared by all three
channels ([10](10-design-decisions.md#the--suffix-is-a-merge-operator-not-a-list-spelling)).
