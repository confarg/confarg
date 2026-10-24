# A flag that stands bare

Some flags are legal with nothing after them.
`--<list>+` appends no items and leaves whatever the lower-priority sources put in the list (`_parse_cli._handle_append_token`, which consumes tokens until the next flag and is content with none).
A varlen collection's own `--<list>` takes zero tokens too and *clears* the collection, as does a union with a sequence variant — the two multi-token branches of `_consume_collection_or_scalar`, named together in `_build._takes_multi_tokens`.
What they share is that vanilla consumes greedily there and asks for nothing, so "zero or more" belongs to the multi-token *shape* rather than to what `"*"` means everywhere: `--config` and `--config.<path>+` carry the same `nargs="*"` and still report `Missing value` when vanilla finds no token.

The config flags stay outside the family on every front-end (BUG-51).
A bare field flag has a job of its own — a bare `--users` *clears* the list — while a bare `--config.<path>+` would mount nothing and reset nothing, so the bare form spells nothing worth accepting, and refusing it is what vanilla always did.
Vanilla's loop raises its own message on every front-end, so argparse's `nargs="*"` — which takes zero tokens — no longer swallows the occurrence; cyclopts validates before its own parse (`_parse_cli._collect_config_file_pairs`, off the one `_missing_config_path_msg` both share), where an implicit token meeting a real one trips a framework assertion. click and typer refuse the bare form in their own parser, with the framework's "requires an argument", as they refuse the whole-value flags.

A refused bare flag and a help flag in one argv are answered **in argv order**: a bare `--config`, `--config.<path>[+]` or fixed-arity flag before `--help` is refused, and a `--help` before it shows help on argparse and cyclopts (BUG-63).
That is argparse's own order — its one-value option refuses `--x --help` before `--help` runs, and shows help on `--help --x` — and the order vanilla's loop refuses in, so `--config --help` answers alike on all five front-ends.

argparse used to show help on `--config --help` and `--pair --help` alone: the loop's refusal runs only once `parse_args` has returned, and argparse's eager `--help` exits inside it.
The spec now says what a bare occurrence raises (`FlagSpec.bare_refusal` — `bare_error`, set on every config-file spec by `_build._config_file_spec` off `_missing_config_path_msg`, or the missing-value error of a spec that `refuses_bare`), and argparse registers such a flag with an action (`_register._RefusingBareAction`) that raises it when argparse hands the occurrence no value.
Actions run in argv order, so the refusal comes before a later `--help` and never before an earlier one. argcomplete runs only the actions it knows, so completion never reaches the refusal.

cyclopts lets its own help and version flags win wherever they sit, but confarg's pre-parse refusals run before cyclopts parses, so `_collect_config_file_pairs` and `refuse_bare_occurrences` read argv only up to the first of the app's help or version flags (`cyclopts._context._before_eager_flag`): an argv that names `--help` first reaches cyclopts' own help, and one that names the bare flag first is refused as everywhere else.

click and typer are the **approved divergence** (BUG-63): their parser refuses an option's missing value before any eager callback runs, so `--help --config` exits with the framework's own usage error, as `--help --x` does on any of their own options.
Making help win there would mean dropping the bare occurrence from what the parser sees, which turns `--config --help` into help as well; the framework's own answer is the lean [design decisions](../design-decisions/divergence-leans-to-the-backend.md#a-divergence-leans-towards-the-affected-backends-own-idiom) settles.

Rejected for argparse: a pre-parse scan of argv, the way cyclopts does it.
The host calls `parse_args` itself, so the one place confarg could scan before the parse is `populate_parser`, and that argv is only what the registration was told, which may be `[]` or differ from what `parse_args` reads later.
Such a scan would also refuse an argv that names `--help` first, against argparse's own order.
Also rejected: approving help-wins as argparse's idiom, since argparse's own options refuse `--x --help`; and letting cyclopts' help win wherever it sits, its own idiom, since that reopens `--config --help` on cyclopts, which can refuse it.

The loop runs vanilla's subpath check too (`_parse_cli._check_mount_subpath`): a `--config.<subpath>` naming no node of the target is refused on every front-end at parse time (BUG-50, closed), not mounted silently to surface later as an unknown-field error from `build()`.

A subkey or element flag (`--f.key`, `--f.N`) has whatever shape the type it addresses has, so it answers the same predicate: `--map.k` on a `dict[str, list[int]]` and `--grid.0` on a `list[list[int]]` stand bare and store the empty collection, while the same flags over a scalar value type take exactly one token.
Asking the predicate rather than the syntax is what keeps that half in: click and typer refused those two spellings while the other three front-ends took them, the same gap the field flag had (BUG-38).

Neither clicklike framework can express a flag that takes zero *or* more tokens: click and typer fix an option's token count when the option is built, and the `multiple=True` the adapters map `"*"` to always demands one.
So a bare `--input+` was rejected with `Option '--input+' requires an argument.` on both, while vanilla, argparse and cyclopts accepted it (BUG-33), and a bare `--input` was rejected the same way (BUG-38). cyclopts reads a bare occurrence as an implicit empty container and needs no help with it alone — but asserts (`argument/_argument.py`, "implicit value, yet more than one token") the moment that implicit token meets a real one, and rejects a second bare occurrence as a repeat.

So the spec keeps the multi-token shape and says, in `FlagSpec.stands_bare`, that the flag is *also* legal with nothing after it; **the framework is handed an argv without the bare occurrences** (`cli._argv.drop_bare_occurrences`).
So the no-op is honored rather than rejected, one argv may spell the same append both ways (`--users+ billy --users+`), and every front-end answers alike (BUG-35).

Dropping a token is safe because nothing reads the framework's parse result for a value: the adapters' CLI channel is vanilla's loop over the argv the user typed ([argv is the only writer](model.md#argv-is-the-only-writer)), and that argv still holds every bare occurrence.
A bare append, subkey or element flag, a bare field flag's clear, and the union shaper's missing value on a bare occurrence that meets an empty accumulation are all read exactly where vanilla reads them, by the same code.
Before REF-72 the parse result *was* the writer for field flags, and each family needed a reader of its own to put back what the drop took (`_bare_multi_token_flags`, `bare_only_flag_names`, `_union_seq_occurrence_writes`).

The predicate reads the opposite family too: a plain fixed-arity flag's bare occurrence is a missing value, not a no-op, so nothing drops it — `refuse_bare_occurrences` raises vanilla's error for one off the argv the user typed, before a framework that would assert on it parses ([whole-value flags](whole-value-flags.md#whole-value-flags)).
`drop_bare_occurrences` and `refuse_bare_occurrences` ask one `_bare_occurrence` predicate, so they cannot disagree about which occurrences are bare.

`_takes_multi_tokens` is the gate registration asks, through the one shape decision every flag of a type takes (`_build._shaped`).
It is the multi-token *shape* and not "is there something to clear": a union with a sequence variant but no varlen one (`str | tuple[str, str]`, or `Pt | Inner` beside a struct) is therefore included, and the empty value it stores is what raises vanilla's error in `_parse_cli._union_seq_value` — so the bare form is refused with confarg's own message everywhere instead of the framework's.
The optional spelling of a fixed-arity field answers the predicate the same way — `tuple[int, int] | None` and a namedtuple under `Optional` are unions with a sequence variant — so its flag registers `stands_bare` like the rest of the family (BUG-79; until then the clicklike parsers answered its bare occurrence with their own usage error) ([whole-value flags](whole-value-flags.md#whole-value-flags)).

It is one rule with one decision-maker and two application points, because the seam at which a framework receives argv differs — as it does for [`cli_prefix`](../cli-parsing/cli-prefix.md#cli_prefix), recorded per framework on whatever survives into the merge step. cyclopts hands confarg the parse itself, so `merge_app` filters the tokens it passes to `App.parse_args`.
In click and typer the *host* calls the command, so the hook rides on the options (`_clicklike.StandsBareMixin`): `add_to_parser` arms a filter on the parser instance, which both frameworks build fresh per parse.
A hook on the command would not survive the `params` copying that groups and decorators do routinely. argparse and vanilla are exempt: `nargs="*"` already takes zero tokens and accepts a second occurrence, so they parse the argv as typed.

"Carries an item" is asked with `_parse_cli._looks_like_flag`, the same value/flag split vanilla consumes by, so the frameworks take exactly the tokens vanilla takes.
That matters for dash-prefixed items in particular: `--input+ -8` carries an item by vanilla's reckoning and is kept, and `--input+=--a` carries its item by construction — a `=` token never matches a bare occurrence.

Only a flag whose spec sets `stands_bare` is filtered, which is why the rule is a marker rather than a syntax rule about trailing `+`: vanilla *rejects* a bare `--config.<path>+` (`Missing file path after --config`), so the config-file append flags must not inherit it.
The scalar root flag clears the marker along with the rest of the multi-token shape, since `_handle_scalar_root` consumes exactly one token whatever the root type is ([CLI parsing](../cli-parsing/cli-prefix.md#cli_prefix)).

Rejected: click's own optional-value spelling (`is_flag=False` plus a `flag_value`).
It fits click alone — typer's vendored parser dropped the feature, so typer would have stayed red — and it changes how click reads the token *after* the flag, treating anything beginning with `-` as an omitted value.
That breaks `--tags+=--a` and `--input+ -8`, which the dashed-value escape requires ([design decisions](../design-decisions/equals-escapes-a-dashed-value.md#the--form-is-the-escape-for-a-dashed-value), `TestDashPrefixedValueContract`).

Also rejected: letting the spec shape follow argv — registering a value-less `nargs=0` when no occurrence carries an item (how BUG-33 was first fixed).
It answers the same question the filter answers, and only for the homogeneous half of it, so the mixed argv stayed broken and the two rules would have had to agree forever.

Also rejected for the collection flag: putting the empty value into the flat dict for *every* bare occurrence, with no field-type gate.
It needs no type walk, but it would quietly accept the bare forms vanilla refuses — `--db` on a struct field, `--map` on a dict — wherever a framework happened not to reject them first.
