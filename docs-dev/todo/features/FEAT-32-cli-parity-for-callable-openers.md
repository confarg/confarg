---
filed: 2026-10-06
where:
  - src/confarg/cli/_build.py
  - src/confarg/_parse_cli.py
  - src/confarg/cli/argparse/_register.py
  - src/confarg/cli/click/_register.py
  - src/confarg/cli/typer/_register.py
  - src/confarg/cli/cyclopts/_register.py
  - src/confarg/cli/_clicklike/_register.py
effort: L
risk: medium
impact: behavior
severity: major
blocked_by: [FEAT-31]
---
# FEAT-32 — CLI parity for `bind`, `call`, `class` and `classfn` in all five adapters

Flags for the new forms: `--f.bind <target>`, `--f.call <target>`, `--f.call.classfn <C.m>`,
and `--f.call.<init arg>` for the owner, plus `--f.<method arg>` for the method's siblings.
Every adapter (argparse, click, typer, cyclopts, and the shared click-like code) must produce the
same merged dict for the same inputs. `_parse_cli.py` and `_build.py` do the discovery.

FEAT-30 already moved registration to the new grammar: `--f.bind` is a static opener, and every
mode discovers its target's parameters as `--f.<p>` (a `class` target's constructor only). Left
here: discovery for a nested target spec, whose keys (`--f.bind.class`, `--f.bind.<ctor arg>`)
merge in every front-end but are registered only when typed, with no help or completion from the
inner target's signature; and everything `classfn` adds.

Parity is checked by the cross-channel contract suite. Add cases for each form, and for a
method whose owner and method share a parameter name, since that is the case the sibling
namespaces exist for.
