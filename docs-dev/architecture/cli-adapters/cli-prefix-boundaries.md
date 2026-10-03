# The cli_prefix boundaries

`cli_prefix` ([CLI parsing](../cli-parsing/cli-prefix.md#cli_prefix)) is a naming convention, not a parsing mode.
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
