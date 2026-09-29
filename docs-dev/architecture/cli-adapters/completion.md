# Completion

Completion must never crash the shell; every failure degrades silently to fewer
suggestions.

- argparse (`argcomplete`): `setup_completion` pre-extends the parser with the fields of
  union classes already determinable from `--config` files or `--f.class` on the partial
  command line, and with callable bind flags. Cheap no-op outside completion mode.
- click: `setup_completion` reads `COMP_WORDS`/`COMP_CWORD` (bash, zsh) and adds dynamic
  flags. Fish is not supported yet.
- typer: the same shared hook, wired through typer's `autocompletion` keyword
  ([the clicklike seam](clicklike-seam.md#the-clicklike-seam)).
- cyclopts: no confarg completion support.
