# BUG-99 — The config flag's space-separated multi-file spelling is declined on click and typer, undocumented

**Where:** `docs-dev/architecture/cli-parsing/config-file-flags.md` · **Filed:** 2026-09-30
**Effort:** S · **Risk:** low · **Impact:** none

`--config a.yaml b.yaml` — the `FILE…` run
[config-file-flags.md](../../architecture/cli-parsing/config-file-flags.md#config-file-flags)
spells unconditionally — parses on vanilla, argparse and cyclopts but exits 2 on click and
typer: their `multiple=True` registration binds one path per occurrence, so the repeated form
`--config a --config b` is their only multi-file spelling. The list syntax divergence scopes
its approval to "the multi-token *field* flags"
([list-syntax-divergence.md#list-syntax-divergence](../../architecture/cli-adapters/list-syntax-divergence.md#list-syntax-divergence)),
so the config flag's decline is neither recorded as approved nor pinned by a test — the
contract suite's multi-file tests
(`TestPipelineParity::test_multiple_config_files_merged`) use the repeated form on every
front-end. Fix direction: record it as an approved divergence narrowed to the two clicklike
front-ends, in `config-file-flags.md` and the invariants list, and pin it with a contract
test beside the BUG-75 `=`-spelling tests, keeping the difference visible
([testing.md#list-syntax-split](../../architecture/testing.md#list-syntax-split)).

```console
$ grep -n "FILE" docs-dev/architecture/cli-parsing/config-file-flags.md
3:`--<config_flag>[.subpath][+] FILE…` is intercepted **before** field lookup, so a field with
# the note promises the space-separated run with no front-end qualification; click and typer
# exit on it
```

```python
from dataclasses import dataclass

import click
from click.testing import CliRunner

import confarg
from confarg.cli.click import populate_command


@dataclass
class T:
    host: str = "x"


cmd = click.Command("demo")
populate_command(T, cmd, argv=["--config", "a.yaml", "b.yaml"])
res = CliRunner().invoke(cmd, ["--config", "a.yaml", "b.yaml"])
print("click :", "exit", res.exit_code, "-", res.output.strip().splitlines()[-1])

try:
    confarg.merge(T, argv=["--config", "a.yaml", "b.yaml"], env={})
except Exception as e:
    print("vanilla:", type(e).__name__ + ":", e)

# expected: one verdict on every front-end, or a recorded divergence naming the two that decline
# actual:
#   click : exit 2 - Error: Got unexpected extra argument (b.yaml)
#   vanilla: InvalidConfigFileError: Config file not found: ...\a.yaml
# (vanilla reached the reader — its space-separated run parsed; click never did)
```
