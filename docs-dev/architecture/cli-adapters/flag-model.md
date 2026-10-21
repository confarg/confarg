# Framework-neutral flag model

`FlagSpec` (name, `nargs`, choices, metavar, help, note, group, completer) is the contract between spec generation and the adapters.
`nargs`: `None` = one value, `"*"` = zero or more, `int` = exact count, `0` = value-less switch (deletes).
Each adapter re-expresses it (argparse `nargs`/`store_true`; click `multiple=True`/`is_flag`; cyclopts `consume_multiple`/`n_tokens`/`bool`).
Three flags qualify what `nargs` alone cannot say: `whole_value` ([whole-value flags](whole-value-flags.md#whole-value-flags)), `stands_bare` ([a flag that stands bare](a-flag-that-stands-bare.md#a-flag-that-stands-bare)) and `refuses_bare` (a bare occurrence is a missing value, refused before a framework that would assert on it parses — [whole-value flags](whole-value-flags.md#whole-value-flags)), each honored by the adapters whose framework can.

`FieldMeta` (via `Annotated`) adds help and metavar without a custom field type.
Help text priority: `FieldMeta.help` > attribute docstring (read from source with `ast`; unavailable for dynamically created classes) > empty.
That prose is `FlagSpec.help`; what confarg adds to it — the default, the positional order, the none hint — is `FlagSpec.note`, kept apart so an adapter can escape confarg's text for its framework's help format without escaping the author's ([framework specifics](framework-specifics.md#help-text-is-format-neutral)).

Which shape a flag takes is one decision, `_build._shaped`, asked of the type the flag sets as resolved: a run that stands bare, a fixed count that takes a whole value and refuses its bare occurrence, or one token.
Every flag that sets a value goes through it — a field, a namedtuple's arity flag, a subkey or element, a class's field or a target's argument — so a type has one shape wherever it is addressed.
Five sites once decided it apart, and the ones that missed a shape registered one token where vanilla's loop took a run: an element flag over a fixed-arity type (BUG-198), a namedtuple or `Optional` fixed-arity field of a class argv names (BUG-233's fix had built them through a leaf builder with neither shape), and a union holding a sequence beside a struct (PR-77, BUG-21).

A non-struct root's bare flag goes through it too, since vanilla's loop consumes the root's value as it consumes a field of its type ([CLI parsing](../cli-parsing/cli-prefix.md#cli_prefix), BUG-177).
It was the one flag forced to a single token whatever its type collected, by an inverse of the shape vocabulary, `FlagSpec.as_single_token()` (REF-68): that inverse had lapsed attribute by attribute before REF-68 gathered it, and it went with its last caller.

`_spec.py` (the model) and `_build.py` (spec generation) live in `cli/`, beside the other two modules every adapter shares, `_prefix.py` and `_collect.py`; `cli/argparse/` holds only what speaks argparse.
They grew out of the argparse backend and sat under `cli/argparse/` until REF-1 moved them.
That was not only tidiness: while `confarg.cli` re-exported from `confarg.cli.argparse._build`, importing the neutral model executed the argparse package's `__init__`, so a click or cyclopts user paid for `_register.py`, `_namespace.py` and `_completion.py` to be imported.
`confarg.cli` is now the only export path for the four neutral names (`FlagSpec`, `FieldMeta`, `build_static_flags`, `build_dynamic_flags`) and `confarg.cli.argparse` deliberately does not alias them, so `import confarg.cli.click` leaves `confarg.cli.argparse` out of `sys.modules` entirely.
The rule that `_build.py` must not import argparse predates the move and outlives it — it is what kept the module movable.

`_build.py` imports `_parse_cli` inside functions: importing it at module level would create a load-time import cycle.
