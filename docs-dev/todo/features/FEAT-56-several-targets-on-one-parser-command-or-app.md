---
filed: 2026-10-24
where:
  - src/confarg/cli/_sources.py::refuse_a_second_target
  - src/confarg/cli/_sources.py::Registration
  - src/confarg/cli/argparse/_register.py::populate_parser
  - src/confarg/cli/_clicklike/_register.py::populate_command
  - src/confarg/cli/cyclopts/_register.py::populate_app
effort: M  # inferred: a record keyed by target in each of the four holders, and a merge that looks its target up
needs_design: true
risk: medium
impact: behavior
severity: trivial  # no use known; a dataclass holding both sections covers the case
---

# FEAT-56 — Several confarg targets on one parser, command or app

A parser, a command or an app holds one confarg target: `populate_*` refuses a second one, because what it records for the merge (the prefix, the sources read, the runs bound) is one record per holder ([a node types its keys by the class it names](../../architecture/design-decisions/a-node-types-its-keys-by-the-class-it-names.md#the-adapters), BUG-273).
A dataclass holding a field of each type covers two configuration sections, with the same flag spellings, and lets an expression in one read the other.

What it cannot give, and a record keyed by target would: an environment prefix per section (`SRV_PORT`, `DB_HOST` where the wrapper reads `APP_SERVER__PORT`), and a section a library registers on a host's parser without the host's dataclass knowing it.
Precedent: jsonargparse's `add_class_arguments(Cls, nested_key=...)` puts several classes on one parser, each under its own key.

Open before this becomes work: whether any user needs it; how argparse's `Namespace` would carry several records (one dict keyed by target, read by `from_namespace(target, ns)`); and whether two targets may share a prefix, which their flags would then collide in.
