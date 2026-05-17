---
filed: 2026-10-17
where:
  - src/confarg/_defaults.py::MergeOptions
  - src/confarg/_api.py
  - src/confarg/cli/argparse/_register.py::populate_parser
  - src/confarg/cli/argparse/_namespace.py::from_namespace
  - src/confarg/cli/_clicklike/_register.py::populate_command
  - src/confarg/cli/cyclopts/_register.py::populate_app
  # plus a new public class
effort: L  # a new public seam, but its design axes are few: what it holds, and which calls it replaces
needs_design: true
risk: low
impact: behavior
severity: minor
---
# FEAT-47 — A confarg object holding the target and its sources

A program that loads its configuration through an adapter names the target type twice, to `populate_*` / `make_parser` and to `merge_*` / `from_*`, and the sources reach the merge through a record `populate_*` leaves on the parser, the command or the app ([a node types its keys by the class it names](../../architecture/design-decisions/a-node-types-its-keys-by-the-class-it-names.md#the-adapters)), which a mismatch error guards. A program calling `merge()` then `build()` repeats the target and `union_tag`. The repetition and the hidden record are ceremony a stateful object would replace.

A stateful object would hold them once: the target type, `files`, `env` / `env_prefix` / `env_separator` / `env_config`, `config_flag`, `cli_prefix`, `union_tag`, the argv, and offer `merge()`, `build()`, `load()` and the adapters' `populate` / `from_*` as methods. Precedents to weigh: jsonargparse's `ArgumentParser`, which owns every source; pydantic-settings' `SettingsConfigDict`, declared on the settings class; click's `Context`, which carries `auto_envvar_prefix` down the command tree; Hydra's `compose()` with `initialize()` holding the config path.

Open before this becomes work: whether the object replaces the functions or sits beside them as one more spelling (one option set, [api-seams](../../architecture/pipeline/api-seams.md#one-option-set)); whether it is per target or per application (one object per `populate_*` call, or one holding several subcommands' targets); whether it caches anything between calls (the parsed files, the environment it read — today the merge re-reads the environment); and how it meets FEAT-19's app-declared defaults, which also want a place where the app speaks once.
