---
filed: 2026-11-09
where:
  - src/confarg/_api.py::load
  - src/confarg/_parse_cli.py::_parse_cli
  - src/confarg/cli/_spec.py::FlagSpec
effort: M
needs_design: true  # whether vanilla prints help at all, from which flag model, and what a field named `help` does
risk: medium  # vanilla only; the adapters keep their frameworks' help
impact: behavior
severity: minor  # workaround: load through an adapter, whose framework prints the help
---

# FEAT-65 — `load()` answers `--help`

`confarg.load(Config, argv=["--help"])` raises `UnknownArgumentError: Unknown argument: '--help' (field 'help' not found)` (run).
The README's getting-started path is `confarg.load()`, so the first `myapp --help` a newcomer types fails; help exists only through the argparse, click, typer and cyclopts adapters.

The design pass decides whether vanilla prints help or keeps refusing it on purpose, and if it prints it: from the framework-neutral flag model the adapters register from ([flag model](../../architecture/cli-adapters/flag-model.md#framework-neutral-flag-model)), how it exits, and how a target with a field named `help` keeps that field.
Precedents: jsonargparse and tyro, the two libraries in [the comparison](../../../docs/comparison.md) that are their own parser, print help, as argparse does.
See [the value-proposition plan](../plans/value-proposition.md#build-order).
