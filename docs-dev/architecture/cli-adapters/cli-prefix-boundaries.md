# The cli_prefix boundaries

`cli_prefix` ([CLI parsing](../cli-parsing/cli-prefix.md#cli_prefix)) is a naming convention, not a parsing mode.
It is applied and removed at two boundaries, and nothing in between knows about it:

| Boundary | Direction | Function |
|---|---|---|
| `populate_*` | out | `_prefix.apply_prefix` renames every `FlagSpec` |
| `merge_*` | in | vanilla's loop strips it from argv itself (`_parse_cli._strip_cli_prefix`, skipping the host's flags outside it); `_prefix.strip_flat_prefix` and `_prefix.strip_argv_prefix` for the argv check |

That works because `FlagSpec.name` carries no `--` and each adapter builds its flag string at exactly one site, while the flat parse result is keyed by that same dotted name. argv must be stripped too, not parameterised: the registration and completion scans resolve dotted paths against the target type, which knows nothing of the prefix.
The strippers are **lenient**, as the loop's `host_parsed` mode is — a flag outside the prefix is the host's, not a typo — and they drop a foreign flag together with its values, so the left-to-right order the scans depend on survives.

A nameless `FlagSpec` is the scalar root: `apply_prefix` turns it into the bare `--<prefix>` flag, and drops it when there is no prefix; vanilla's loop reads the bare `--<prefix>` as the scalar root, at the empty path `_ParseCtx.write` lands under `__root__`.
The parse result's key for it, `""` once the prefix is stripped, is the root's and never the host's: `_collect._require_argv_spells` counts it spelled when argv spells the bare prefix flag, which the argv stripper drops, rather than asking the walk of it, which a dict root answers as a key path below the root (the parse result of `--app '{"a": 1}'` was refused as one argv does not spell, on every adapter).

`_prefix.in_prefix` is the one spelling of a name under the prefix — `apply_prefix` renames with it, and so does completion when it puts a scanned path back under the prefix.
Before, completion spelled it on its own and turned a root union's tag, whose path is empty, into `--app..host` flags.

`populate_*` records the prefix so `merge_*` can recover it, on whatever survives into the merge step — which differs per framework, since none of the four hands the merge step the object the flags were registered on: argparse gets only a Namespace, so it rides there via `set_defaults`; click and typer commands get their `params` copied onto other commands, so it rides on the options; cyclopts hands back the App, so it lives in `_app_meta`.
`resolve_prefix` is the one place the recovered and the passed value are reconciled.

## Help names a flag as typed

`apply_prefix` renames a spec, not its help, and the help may hold the user's own prose, so it cannot be rewritten after the fact.
A help string confarg writes therefore names a concrete flag only where it knows the prefix: the root `--config` help is written by `build_static_flags`, which has `cli_prefix`, and spells `--app.config.FIELD` through `in_prefix`.
A help written inside the struct walk, which knows no prefix, names no flag: a union tag's help says "use that class's field flags", as the subclass and root-union tag helps already did, and a callable opener's says `--FLAG.PARAM`, a placeholder.
Before, a union tag under `cli_prefix="app"` pointed at `--pet.<field>` flags that only exist as `--app.pet.<field>`.

Rejected: **threading `cli_prefix` through the struct walk**, so every writer can spell the full flag.
It is precise, but the walk is deliberately prefix-blind (it resolves against the target type, above) and the prefix would ride along only for help text.

Rejected: **rewriting `--…` mentions in `apply_prefix`**.
A `FieldMeta.help` or a docstring may name the host's own flags, which are outside the prefix and must stay as written.
