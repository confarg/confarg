# The adapter model

## Why adapters exist

confarg parses argv itself; an application needs no CLI library. The adapters exist so
users can keep their favorite CLI library (help, completion, subcommands) while confarg
still owns configuration semantics. They are a translation layer, never a second
implementation: every adapter must produce exactly what `confarg.load()` would
([invariants](../invariants.md#cross-channel-parity)).

## The quartet

| | argparse | click | typer | cyclopts |
|---|---|---|---|---|
| register flags | `populate_parser` (+ `make_parser`) | `populate_command` | `populate_command` | `populate_app` |
| raw dict | `merge_namespace` | `merge_context` | `merge_context` | `merge_app` |
| object | `from_namespace` | `from_context` | `from_context` | `from_app` |

`merge_*` → flatten the framework's result to `{dotted.flag: value}` →
`cli._collect._merge_from_flat`, which is the whole shared tail: check the parse result against
argv (`_require_argv_spells`) → vanilla's loop over argv (`_parse_cli._parse_cli(...,
host_parsed=True)`), which returns the CLI channel and its `--config` files →
`_pipeline._merge_sources`. `from_*` = `merge_*` + `build()`. Only the flattening is
per-adapter, so the four cannot drift. `merge_*` and `from_*` take `confarg.load`'s own
keywords, `**opts: Unpack[MergeOptions]`
([pipeline](../pipeline/api-seams.md#one-option-set)). `populate_*` defaults `argv` to `sys.argv[1:]` like
`merge_*`, so the host parser accepts every flag `merge_*` will consume; `argv=[]` registers
only static flags.

Asymmetry: cyclopts is signature-driven and has no separate parse result to hand over, so
`merge_app`/`from_app` call `app.parse_args` themselves and `sys.exit` on `--help`/`--version`.
Typer is signature-driven too, but it compiles the signature down to a command object, so
`populate_command` takes what `typer.main.get_command(app)` returns and the pair is click's.

## Argv is the only writer

The framework parses argv for what only it can do — validation, `--help`, completion, its own
parameters — and confarg writes the CLI channel from that same argv with the loop vanilla runs
(REF-72). The merged dict then equals vanilla's by construction: values, patches, tags, casts,
the order in which occurrences override each other, and the key order a dump serializes (BUG-87).

The loop runs in `host_parsed` mode, which differs from vanilla in one respect only: a token the
host owns is skipped with its values instead of refused. That is a positional or subcommand
token no flag consumed, a flag outside `cli_prefix`, or, with no prefix, a flag whose first
segment names no member of the target. Anything inside confarg's namespace is parsed exactly as
vanilla parses it, so a flag the registration accepted and vanilla refuses (BUG-112, BUG-113)
raises vanilla's error at merge rather than being dropped. One stray needs the host's answer:
argparse and cyclopts register a multi-token or fixed-arity flag greedily, so the token after
the run vanilla consumes was bound to the flag and is the stray vanilla refuses, while click and
typer bind the exact count, so the same token is a positional of the host's. The adapter says
which (`binds_runs`), and the loop asks `_build._binds_a_run` of the type it consumed for.

The parse result is only *checked*: a confarg flag it holds that argv does not spell means the
two are not one command line — typically `parse_args(custom)` merged with `argv` left to default
to `sys.argv[1:]` — and is refused (`_require_argv_spells`) rather than lost without a word. A
key the target does not resolve is the host's own parameter and is left alone. Precedent: the
`cli_prefix` mismatch, which `resolve_prefix` refuses rather than matching no flag. Nor does
confarg shape the *values* the parse result holds: they are never read, so a rule over them
would be a second writer. `FlagSpec.accumulates` once asked argparse for `action="extend"`
(BUG-37) to keep the Namespace an honest picture of what was typed; it was dropped (REF-76), so
a host application reading the framework's own result sees the framework's native semantics —
argparse's last-wins on a repeated multi-token flag — while the merge accumulates off argv.

Superseded: a flat collector walking the target type over the parse result, with the patch scan
replaying vanilla's loop for patches only (`patch_only`) and the two halves joined by
`_deep_merge`. A parse result has no order, so every rule in which argv order mattered grew a
reader recovering one piece of the loop (`_arity_flag_writes_last`, `_last_leaf_cast_spelling`,
`_tokens_past_whole_field_delete`, `_union_seq_occurrence_writes`, …) and every place where the
two halves met grew a repair (`_promote_patched_lists`, `_restore_patch_deletes`, the scan's
`_pop_nested`). Each reader modeled less than the loop, and the gaps were bugs: interleaved bare
and sub-flags (BUG-111), a cast's order against its plain flag (BUG-95), key order (BUG-87).

The price is that `argv` must be the list the framework parsed. It always had to be for patches
and `--config` order; it now has to be for every value, and the check above makes a mismatch
loud ([limitations](../limitations.md#cli-front-ends)).

## Only user-typed values

Framework defaults never reach the CLI layer, which is written from argv alone. The parse
result must still hold only what the user typed, or the argv check would read a default as a
flag argv does not spell
([argv is the only writer](#argv-is-the-only-writer)). Each framework needs its own mechanism:

- argparse: every argument uses `default=argparse.SUPPRESS`;
- click: `ctx.get_parameter_source(k) == ParameterSource.COMMANDLINE`;
  `allow_from_autoenv=False` so click never reads env itself (confarg does);
- cyclopts: every synthetic parameter defaults to `None`, and `None` values are dropped.
