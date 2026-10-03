# A flag that stands bare

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
[`cli_prefix`](../cli-parsing/cli-prefix.md#cli_prefix), recorded per framework on whatever survives into
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
([CLI parsing](../cli-parsing/cli-prefix.md#cli_prefix)).

Rejected: click's own optional-value spelling (`is_flag=False` plus a `flag_value`). It fits
click alone — typer's vendored parser dropped the feature, so typer would have stayed red —
and it changes how click reads the token *after* the flag, treating anything beginning with
`-` as an omitted value. That breaks `--tags+=--a` and `--input+ -8`, which the dashed-value
escape requires
([design decisions](../design-decisions/equals-escapes-a-dashed-value.md#the--form-is-the-escape-for-a-dashed-value),
`TestDashPrefixedValueContract`).

Also rejected: letting the spec shape follow argv — registering a value-less `nargs=0` when no
occurrence carries an item (how BUG-33 was first fixed). It answers the same question the
filter answers, and only for the homogeneous half of it, so the mixed argv stayed broken and
the two rules would have had to agree forever.

Also rejected for the collection flag: putting the empty value into the flat dict for *every*
bare occurrence, with no field-type gate. It needs no type walk, but it would quietly accept the
bare forms vanilla refuses — `--db` on a struct field, `--map` on a dict — wherever a framework
happened not to reject them first.
