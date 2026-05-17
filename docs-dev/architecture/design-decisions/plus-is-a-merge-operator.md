# The `+` suffix is a merge operator, not a list spelling

Two independent questions hide behind a list flag, and only one of them is a framework's business:

| Axis | Question | Who answers |
|---|---|---|
| spelling | how many tokens does one value take, and how are they written? | the host framework |
| merge | does the lower-priority value survive, or is it replaced? | confarg |

`+` names the **merge** axis alone, and every channel spells it on the path: `--input+ 42` on argv, `APP_INPUT+=42` in the environment, `--config.dbs+ other.yaml` or `APP_CONFIG__DBS+=other.yaml` for a sub-configuration.
A configuration file, whose keys are its paths and its data at once, spells the same op in the value instead, `input: {__append__: [42]}`, so that `input+` stays a key it can hold ([a file spells an op in its value](a-file-spells-an-op-in-its-value.md#a-file-spells-an-op-in-its-value)).
Until FEAT-43 it wrote `input+: [42]`, the suffix on a key.
Dropping `+` from argv to lean on a framework's own repetition instead would split argv from the environment, and from what the file's op means, to save one character.

The corollary is that **nothing else** spreads one value over several list elements.
A mount does not: an `__include__` in a list item, and a `--config.<path>` without the suffix, each contribute exactly one element whatever they load, and `--config.<path>+` is what asks for the fragment's items to be added.
The two used to disagree in opposite directions — a list-rooted file was spliced by `__include__` and wrapped by `--config.<path>+`, which additionally spliced a file whose single key happened to match the mounted key, so a fragment's content depended on where it was mounted ([config files](../config-files/mounting.md#mounting)).
Both are now the same rule, and it is this one.

The temptation is real under click and typer, where repeating a flag is the *only* multi-token spelling, so `--users+ x --users+ y` looks like a longer way to write `--users x --users y`.
It is not.
Over a config file holding `users: [alice, bob]`, click reads the first as `[alice, bob, x, y]` and the second as `[x, y]`: repetition accumulates *within* the CLI channel, and the list it builds then replaces the file at CLI priority.
No front-end, click included, can express an append by repeating a flag — which is exactly why the operator is spelled separately.

The spelling axis diverges per framework and always has ([CLI adapters](../cli-adapters/list-syntax-divergence.md#list-syntax-divergence)).
The merge axis does not, which is why `--f x --f y` reads as `--f x y` in every front-end instead of last-wins in two of them (BUG-37): repetition is a spelling, and a spelling never decides whether the lower-priority value survives.

## The environment spells it in the variable's name

`APP_INPUT+=42` appends, at any depth, as `--input+ 42` does (FEAT-18).
The suffix is on the name, the path side, where every channel spells an op, and never in the value.
It is the spelling the delete already had (`APP_INPUT-`), so the environment has one vocabulary with the other channels.
A variable takes one value, so the flag's several tokens become a JSON array, the flag's own single-token spelling: `APP_INPUT+='[42, 43]'`.
At one path an append applies after a delete, a cast and a plain value ([environment parsing](../environment-parsing.md#the-broader-variable-applies-first)).

Rejected: a value-side marker, `APP_INPUT='@merge [42]'`, the shape dynaconf chose.
It keeps a variable's name exportable from a POSIX shell, which `+` is not, but `-` is not either, and confarg reads a mapping it is handed, not shell syntax.
It would have spelled the append unlike the delete and unlike every other channel, needed an escape for a value that starts with the marker, and put an op in a value rather than on the path.

Until then the root variable was warned about as naming no field and dropped, while one below a dict reached the merge as the key `k+`, which the merge read as a file's `k+:` was then read, and appended (BUG-201).
