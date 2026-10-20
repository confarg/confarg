---
filed: 2026-10-20
where:
  - src/confarg/cli/cyclopts/_register.py::load_flags_into_app
effort: S
risk: low
impact: none
severity: minor  # a wrong usage line in a public docstring
introduced_by: [BUG-233, BUG-236, BUG-110, BUG-114]  # the populate_* signatures moving to **opts
---

# BUG-263 — `load_flags_into_app` documents two parameters it does not take

The public `confarg.cli.cyclopts.load_flags_into_app(flags, app)` lists `config_subkeys` and `**opts` under its `Args:`, copied word for word from `populate_app`'s, though its signature takes neither: a reader following the docstring gets a `TypeError`.
Fix direction: delete the two entries; `populate_app` keeps them.

Origin: regression from the fix for BUG-233, BUG-236, BUG-110 and BUG-114, which moved every `populate_*` from its own `cli_prefix`/`union_tag`/`config_flag`/`argv` keywords to `**opts: Unpack[MergeOptions]` and rewrote their `Args:` sections; the new text landed in the neighbouring `load_flags_into_app` docstring as well.
It is the only `load_flags_into_*` affected.

```console
$ grep -n "config_subkeys\|\*\*opts" src/confarg/cli/cyclopts/_register.py
211:        config_subkeys: Whether to register ``--<config_flag>.<path>`` options for
214:        **opts: The sources the options are typed by and how to read them, as for
273:    config_subkeys: bool = True,
274:    **opts: Unpack[MergeOptions],
288:        config_subkeys: Whether to register ``--<config_flag>.<path>`` options
291:        **opts: The sources the options are typed by and how to read them, as for
316:        config_subkeys=config_subkeys,
```

Expected: lines 211 and 214 do not exist — they sit in `load_flags_into_app`'s docstring (signature at line 194: `def load_flags_into_app(flags: list[FlagSpec], app: cyclopts.App) -> None`); only `populate_app` (signature at 273–274, docstring at 288–291) takes the two parameters.
