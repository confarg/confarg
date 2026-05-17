# Framework-neutral flag model

`FlagSpec` (name, `nargs`, choices, metavar, help, note, group, completer) is the contract between spec generation and the adapters.
`nargs`: `None` = one value, `"*"` = zero or more, `int` = exact count, `0` = value-less switch (deletes).
Each adapter re-expresses it (argparse `nargs`/`store_true`; click `multiple=True`/`is_flag`; cyclopts `consume_multiple`/`n_tokens`/`bool`).
Three flags qualify what `nargs` alone cannot say: `whole_value` ([whole-value flags](whole-value-flags.md#whole-value-flags)), `stands_bare` ([a flag that stands bare](a-flag-that-stands-bare.md#a-flag-that-stands-bare)) and `refuses_bare` (a bare occurrence is a missing value, refused before a framework that would assert on it parses — [whole-value flags](whole-value-flags.md#whole-value-flags)), each honored by the adapters whose framework can.

`FieldMeta` (via `Annotated`) adds help and metavar without a custom field type.
Help text priority: `FieldMeta.help` > attribute docstring (read from source with `ast`; unavailable for dynamically created classes) > empty.
That prose is `FlagSpec.help`; what confarg adds to it — the default, the positional order, the none hint — is `FlagSpec.note`, kept apart so an adapter can escape confarg's text for its framework's help format without escaping the author's ([framework specifics](framework-specifics.md#help-text-is-format-neutral)).

The model owns the inverse of that shape vocabulary, too: `FlagSpec.as_single_token()` clears `nargs`, `whole_value` and `stands_bare` in one operation, spelled beside the attributes themselves.
A flag forced to a single token — a non-struct root's, which takes exactly one whatever its type collects ([CLI parsing](../cli-parsing/cli-prefix.md#cli_prefix)) — is therefore reshaped where the shape is declared, and the next shape attribute is undone where it is added rather than cleared by each caller by hand, one attribute at a time (REF-68).
That reset is what once lapsed attribute by attribute: a fixed-tuple root kept `whole_value`, which made argparse register the bare prefix flag greedily, because nothing tied the reset to the shape it undoes.

`_spec.py` (the model) and `_build.py` (spec generation) live in `cli/`, beside the other two modules every adapter shares, `_prefix.py` and `_collect.py`; `cli/argparse/` holds only what speaks argparse.
They grew out of the argparse backend and sat under `cli/argparse/` until REF-1 moved them.
That was not only tidiness: while `confarg.cli` re-exported from `confarg.cli.argparse._build`, importing the neutral model executed the argparse package's `__init__`, so a click or cyclopts user paid for `_register.py`, `_namespace.py` and `_completion.py` to be imported.
`confarg.cli` is now the only export path for the four neutral names (`FlagSpec`, `FieldMeta`, `build_static_flags`, `build_dynamic_flags`) and `confarg.cli.argparse` deliberately does not alias them, so `import confarg.cli.click` leaves `confarg.cli.argparse` out of `sys.modules` entirely.
The rule that `_build.py` must not import argparse predates the move and outlives it — it is what kept the module movable.

`_build.py` imports `_parse_cli` inside functions: importing it at module level would create a load-time import cycle.
