# Command-line parsing (vanilla)

`_parse_cli.py` is the vanilla argv parser used by `confarg.merge()`. The adapters reuse
parts of it (the `--config` scan, the patch-only mode, the type walk); see
[CLI adapters](../cli-adapters/README.md).

| Note | What it holds |
|---|---|
| [type-guided-parsing.md](type-guided-parsing.md) | why a dotted path is resolved against the target type rather than parsed as `key=value` |
| [token-consumption.md](token-consumption.md) | how many tokens a flag takes and what they become: the value/flag split, repetition, unions with sequence variants, callable paths |
| [casts-and-reserved-words.md](casts-and-reserved-words.md) | the `.str`/`.int`/`.json` suffixes, and the rule that a real field always beats a reserved word |
| [collection-patches.md](collection-patches.md) | `--f+`, `--f.N`, `--f.N-`, `--f.key`, and the three spellings that clear a list |
| [config-file-flags.md](config-file-flags.md) | `--config[.subpath][+]`, intercepted before field lookup |
| [cli-prefix.md](cli-prefix.md) | `cli_prefix`, and what a scalar root's only CLI spelling is |
