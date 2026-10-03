# The `+` suffix is a merge operator, not a list spelling

Two independent questions hide behind a list flag, and only one of them is a framework's business:

| Axis | Question | Who answers |
|---|---|---|
| spelling | how many tokens does one value take, and how are they written? | the host framework |
| merge | does the lower-priority value survive, or is it replaced? | confarg |

`+` names the **merge** axis alone, and names it the same way in every channel that has one:
`--input+ 42` on argv, `input+: [42]` as a config-file key, `--config.dbs+ other.yaml` for a
sub-configuration. Dropping it from argv to lean on a framework's own repetition instead would
split one vocabulary across three channels to save one character.

The corollary is that **nothing else** spreads one value over several list elements. A mount
does not: an `__include__` in a list item, and a `--config.<path>` without the suffix, each
contribute exactly one element whatever they load, and `--config.<path>+` is what asks for the
fragment's items to be added. The two used to disagree in opposite directions — a list-rooted
file was spliced by `__include__` and wrapped by `--config.<path>+`, which additionally spliced
a file whose single key happened to match the mounted key, so a fragment's content depended on
where it was mounted ([config files](../config-files/mounting.md#mounting)). Both are now the same rule, and it
is this one.

The temptation is real under click and typer, where repeating a flag is the *only* multi-token
spelling, so `--users+ x --users+ y` looks like a longer way to write `--users x --users y`. It is
not. Over a config file holding `users: [alice, bob]`, click reads the first as
`[alice, bob, x, y]` and the second as `[x, y]`: repetition accumulates *within* the CLI channel,
and the list it builds then replaces the file at CLI priority. No front-end, click included, can
express an append by repeating a flag — which is exactly why the operator is spelled separately.

The spelling axis diverges per framework and always has
([CLI adapters](../cli-adapters/list-syntax-divergence.md#list-syntax-divergence)). The merge axis does not, which is why `--f x --f y`
reads as `--f x y` in every front-end instead of last-wins in two of them (BUG-37): repetition is a
spelling, and a spelling never decides whether the lower-priority value survives.

The environment is the one channel the suffix does not reach — an append has no env spelling at
all, though a delete does (FEAT-18).
