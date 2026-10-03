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

## Only user-typed values

Framework defaults must never enter the CLI layer, or they would override config files and
env at the highest priority. Each framework needs its own mechanism:

- argparse: every argument uses `default=argparse.SUPPRESS`;
- click: `ctx.get_parameter_source(k) == ParameterSource.COMMANDLINE`;
  `allow_from_autoenv=False` so click never reads env itself (confarg does);
- cyclopts: every synthetic parameter defaults to `None`, and `None` values are dropped.
