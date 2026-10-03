# Whole-value flags

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
([types](../types/leaf-coercion.md#leaf-coercion)). The two disagree on a registered leaf
with an `__init__` — `UUID`, say — and this question comes first: an explicit tag naming
such a class still builds it from its fields
([design decisions](../design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in)), and the tag cannot be
seen until the token is decoded. Refusing the token here would put that hatch out of the
CLI's reach while leaving it open to env and files, and would silently coerce the JSON
*text* into a leaf instead. `cli/_collect.py` therefore honors the decoded whole value in
its registered-leaf branch before falling back to scalar coercion, the order vanilla's
`_consume_value` already has. A token no blob decodes is kept raw, not dropped: vanilla's
`_consume_value` stores it for `build()` to refuse (`--inner 7` → `{'inner': '7'}` →
`expected dict, got str '7'`), and the collector's struct branch stores the same
`_str_token`, as its dict and union branches already did — the token once vanished there,
and a typo'd CLI value silently built the field's default on four of the five front-ends
(BUG-82, closed). The `--help` metavar stays `VALUE` there: the rule is that
`JSON` implies the token is decoded, not the converse, and a registered leaf's ordinary
spelling is its scalar, with the tagged blob an escape hatch rather than the syntax to
advertise.

The flags are **static**, not argv-scanned: the field is declared, so it belongs in `--help`
next to the bare `--tags` / `--pair` flags lists and tuples already get, and completion can
offer it. `nargs=None` — vanilla consumes exactly one token here, rejects a second as a stray
positional, and rejects none at all with `Missing value`
([design decisions](../design-decisions/a-whole-value-flag-needs-its-value.md#a-whole-value-flag-needs-its-value)): the `FlagSpec` vocabulary
deliberately has no optional-value `"?"`, because cyclopts cannot express one. The metavar is `JSON` only where the predicate says the token is decoded, so a field that
keeps its token raw does not advertise a syntax it will not honour. Optionality is not one of
the things that decides this: `dict[str, str] | None` takes the mapping `dict[str, str]` takes,
`Callable[…] | None` takes the spec `Callable[…]` takes, and both get the same `JSON` metavar
([design decisions](../design-decisions/optionality-and-whole-values.md#optionality-does-not-change-what-a-whole-value-accepts)).
The hatch's *flat* spelling crossed the same seam one step later (BUG-56):
`--id.class uuid.UUID --id.hex …` is what the environment says with `ID__CLASS` /
`ID__HEX`, and vanilla accepted it all along because its type walk treats a registered
leaf structurally — the tag segment resolves through the `union_tag` rule, a parameter
through the leaf's `__init__` fields. The adapters now mirror that walk from both sides:
registration is argv-scanned
([static and dynamic flags](static-and-dynamic-flags.md#static-and-dynamic-flags)), accepting exactly what
`_parse_cli._resolve_field_type` accepts — so `--id.bogus` stays unregistered and the
framework's rejection stands in for vanilla's `no_such_field` — and the collector descends
into the leaf as it descends into a struct, writing the tag back raw, before the import
resolves, for the [BUG-45](union-inheritance-and-cast-flags.md#union-inheritance-and-cast-flags) reason. A registered leaf
as the *root* target crossed the same seam one step later (BUG-71): it has no field to
descend from, so the scan's leaf is the target itself, at the empty prefix of the path —
and the tag flag, whose only segment is the tag, registers exactly as a field's does. The
root's `__init__` parameters were static all along — the root is walked structurally,
exactly as a union holding the same leaf is — so the tag is the one flag the scan adds;
and the collector needs no new branch, because the inheritance walk already writes a root
tag back and stops at the base the tag names.

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
([CLI parsing](../cli-parsing/token-consumption.md#token-consumption)). A *delete* flag refines it too, even though it
travels with the patch ops rather than the flat collector: the patch scan is handed the
collected dict and opens the shorthand there as well
([a patch op joins the values the framework collected](collection-patch-parity.md#a-patch-op-joins-the-values-the-framework-collected), BUG-24).

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
([invariants](../invariants.md#cross-channel-parity)). A click `Option` cannot vary its token count:
`nargs=-1` raises `nargs=-1 is not supported for options`, and the only alternative,
`multiple=True`, would buy the whole-value token by taking `--pair 13 42` away and demanding
`--pair 13 --pair 42` in its place. Inline JSON is not what a CLI user reaches for, so click
keeps the readable positional form and declines the whole value, per
[design decisions](../design-decisions/divergence-leans-to-the-backend.md#a-divergence-leans-towards-the-affected-backends-own-idiom). The
divergence is confined to the two clicklike front-ends — typer inherits it along with the
option class it forked ([the clicklike seam](clicklike-seam.md#the-clicklike-seam)); argparse and cyclopts, which *can* vary
the count, get both.

Registering `nargs="*"` hands **arity enforcement back to confarg** — the framework no longer
counts the tokens, so whatever argv held arrives in one list and the count is the collector's
to check. The two bounds are not the same job, and only one of them can be answered here.

What a *repeat* of the flag means is the other half of the greedy registration, and the two
frameworks that vary the count answer it in their own idiom. Argparse's plain store keeps
only the last occurrence by construction. Cyclopts' `consume_multiple=True` accumulates the
token runs of every occurrence into one list — a list that never existed in argv and whose
seams the collector cannot recover — so the same setting cannot serve both jobs: it is what
a varlen list wants (`FlagSpec.accumulates`, [list syntax divergence](list-syntax-divergence.md#list-syntax-divergence)) and what a
fixed-arity flag must not keep. A whole-value spec therefore registers a converter
(`cli/cyclopts/_register._last_occurrence_convert`) that keeps only the last occurrence's
run, read off the `CliToken.index` restart that survives into the converter, so `--pair 1 2
--pair 3 4` is `(3, 4)` on cyclopts as on every other front-end (BUG-62, closed).

Keeping only the last occurrence's run also *hides* the earlier ones: `--pair 1 --pair 3 4`
hands the collector the surviving run `['3', '4']`, both bounds answered, while vanilla
refuses the first occurrence the moment its run stops short. So the bounds are asked of
**every** occurrence's run, read off the argv the user typed by
`cli/_collect._fixed_arity_occurrence_runs` — the same read-back the latest-writer question
performs (`cli/_collect._arity_flag_writes_last`, below) — and a parse result argv cannot
account for falls back to the run the framework handed over. A run ends where vanilla's own
consumption ends, at the next flag-looking token; the value half of `--pair=1` opens its
occurrence's run, and the tokens after it complete it, exactly as vanilla consumes them.
Click and typer count the tokens themselves, so a short occurrence never reaches the
collector there (BUG-73, closed).

Both are parse-time facts, so `cli/_collect._require_fixed_arity` answers both, mirroring the
`_require_value` vanilla asks once per positional token
([CLI parsing](../cli-parsing/token-consumption.md#token-consumption)). It is asked of the field type **as resolved,
without unwrapping `Optional`** — the type vanilla dispatches on: `tuple[X, Y] | None` is a
union with a sequence variant there, consumes greedily, and owes neither bound, so unwrapping
first would make the adapters refuse `--pair 1` where vanilla accepts it.

The **lower** bound: a short token run is `Missing value for '--pair'` and not a shorter tuple,
because a fixed arity is not one of the shapes a bare flag is reserved for
([design decisions](../design-decisions/a-whole-value-flag-needs-its-value.md#a-whole-value-flag-needs-its-value)). The **upper** bound: a token
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

The same rule shapes what the guard's absence leaves in the dict. An `Optional[<sequence>]`
field is a union with a sequence variant to the collector as well, so its flag's tokens go
through `_collect_union_seq_value` — `cli/_collect._collect_ns_optional_seq` routes them there
before the fixed-arity and namedtuple branches the unwrapped core would pick (BUG-61). A bare
occurrence stores the empty run the shaper refuses — `Missing value for '--pair'`, vanilla's
own error, on the front-ends that store it at all (click and typer register the exact count
and refuse the bare form in their own parser, as they do for the plain spelling) — and a valued
run is stored raw, its per-position coercion deferred to `build()` exactly as vanilla's
`_union_seq_value` defers it. A namedtuple's sub-flags keep their spelling across the move,
merged in argv order as on the plain spelling; what differs is the shape a sub-flag written
last descends into: the generic `_set_nested` `'*'` base, because vanilla's by-field-name
promotion asks the field as resolved and finds the union there — so `--pt 1 2 --pt.y 9` under
`Point | None` is `{'*': ['1', '2'], 'y': 9}` on all five front-ends, and `build()` rejects it
on all five alike.

For the namedtuple, `cli/_collect.py` decodes the lone token through
`_fixed_arity_whole_value`, which delegates to the same two decoders the other branches use
(`_json_array_override` for `[…]`, `_accepts_object_value` + `_parse_json_arg` for `{…}`), so
the object form cannot drift from what vanilla decodes. Sub-flags refine it exactly as they
refine a struct's whole value — by name over a decoded object, by position otherwise — and
their values are coerced to their field's type as vanilla's own dispatch coerces them, so a
sub-flag feeds an expression the number it spelled and not its text (BUG-66).

A sub-flag is stored under the key the user spelled, name and index alike (BUG-65): vanilla
writes each flag at its own key and leaves construction to reconcile them, so
`--pt.x 13 --pt.0 9` reaches the merged dict as `{'x': 13, '0': 9}` — and `build()` owns the
win, constructing an all-index dict positionally and refusing a mixed one with
`Unknown field(s)`. The collector once re-keyed an index flag under its field name, a
collection-time priority vanilla never makes, which rewrote keys vanilla keeps and dropped a
`--pt.0` a `--pt.x` rode with. The join with the arity flag's positions keeps that half
vanilla's shape too: the positions are re-keyed by field name, as
`_parse_cli._promote_namedtuple_positional` re-keys them, and the sub-flags are laid on top
at their own keys — `--pt 1 2 --pt.0 9` is `{'x': 1, 'y': 2, '0': 9}`, the mixed spelling
`build()` refuses, on all five front-ends alike.

The *order* the two halves arrived in is read back off argv, where a framework's parse
result cannot carry it: the arity flag is the latest writer exactly when its last
occurrence follows the last sub-flag's (`cli/_collect._arity_flag_writes_last`, the
read-back the patch and `--config` scans already perform), and then it overwrites the
field wholesale — `--pair.y 7 --pair 13 42` is `[13, 42]`, the sub-flag gone, while the
reverse order joins the two halves by field name. Latest arguments overwrite earlier
ones ([design decisions](../design-decisions/namedtuple-arity-flag-argv-order.md#a-namedtuples-arity-flag-and-its-sub-flags-merge-in-argv-order)).

A sub-flag one level below a struct-shaped field — a struct, or another namedtuple,
however wrapped — is not a scalar, and the two spellings of such a field take what that
field type takes at any other depth (BUG-68): the static walk recurses into them as it
recurses into a struct's fields, so `--pt.inner.a` registers next to `--pt.inner`, under
the index spelling too. The collector routes both spellings through the one per-field
dispatch a struct's own fields go through (`cli/_collect._collect_field`), with
`_namedtuple_deep_fields` naming which fields count as deep, and the writes land on the
paths the flags spell — so a deep sub-flag refines a whole value's decoded object key by
key, as a struct's sibling flags do, rather than replacing the sibling dict a pre-merged
value would. The priority above is unchanged a level down: the arity flag typed last
takes the field wholesale, its own arity flag included, and a deep sub-flag typed last
descends into whatever the arity flag left — the by-field-name promotion first, then the
deep write.

Everything else about a namedtuple is shared — the arity flag, the per-field and per-index
flags, and the vanilla positional form
([design decisions](../design-decisions/namedtuple-is-a-fixed-length-sequence.md#a-namedtuple-is-a-fixed-length-sequence)).

A dict field's bare flag is its *only* static flag (its keys are unknown until argv is read);
subkeys arrive as patch flags and are deep-merged over the whole value, so
`--env '{"a":"b"}' --env.c d` yields `{"a": "b", "c": "d"}` as in vanilla.

Limitation, shared with [collection patches](collection-patch-parity.md#collection-patch-parity): a framework's parse
result carries no argv order, and only the namedtuple's arity flag reads the order back off
argv (above). A struct or dict whole value is always refined by its sibling
`--<field>.<sub>` flags, so `--sub.a 3 --sub '{"a":2}'` disagrees with vanilla, which honors
argv order. The useful order — whole value first, refinements after — agrees.
