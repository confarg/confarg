---
filed: 2026-11-12
where:
  - src/confarg/cli/typer/_completion.py::setup_completion  # passes the plain _spec_to_option
  - src/confarg/cli/typer/_register.py::_option_factory
effort: S
risk: low
impact: behavior  # the help a completion lists for a dynamic flag changes to the escaped spelling
severity: trivial  # a bracket in a dynamic flag's name makes the completion help differ from the registered one; no error
introduced_by: [BUG-226]  # PR-397, which escaped the help in _option_factory and left the completion path out
---

# BUG-336 — Typer's completion registers a dynamic flag with unescaped help

`typer/_register.py::populate_command` registers every option through `_option_factory(command)`, which escapes confarg's help for the markup typer renders it in (`rich_markup_mode`, BUG-226).
`typer/_completion.py::setup_completion` hands the shared `_clicklike.setup_completion` the plain `_spec_to_option`, so the dynamic flags it adds while completing carry the help unescaped, where the same flag registered by `populate_command` carries it escaped.
Fix direction: pass `_option_factory(command)` there, the one factory both paths register through ([clicklike seam](../../architecture/cli-adapters/clicklike-seam.md#the-clicklike-seam)); the change looks evident, one argument and a test beside the typer completion tests.

Origin: latent since PR-194, which added the typer front-end with the plain factory in both places; PR-397 (BUG-226) then made `populate_command` build its factory from the command and did not touch `setup_completion`, so the two paths diverged there.

```python
import os
from dataclasses import dataclass, field

import typer

from confarg.cli.typer import populate_command, setup_completion


@dataclass
class Cfg:
    extras: dict[str, list[str]] = field(default_factory=dict)


def command():
    app = typer.Typer(rich_markup_mode="rich")

    @app.command()
    def main(ctx: typer.Context) -> None:
        pass

    return typer.main.get_command(app)


argv = ["--extras.[b]+", "a"]
registered = command()
populate_command(Cfg, registered, argv=argv)
completing = command()
populate_command(Cfg, completing, argv=[])
os.environ["_MAIN_COMPLETE"] = "bash_complete"
os.environ["COMP_WORDS"] = " ".join(["main", *argv, "--"])
os.environ["COMP_CWORD"] = str(len(argv) + 1)
completing.name = "main"
setup_completion(completing, Cfg)
for label, cmd in (("populate_command", registered), ("setup_completion", completing)):
    print(label, [p.help for p in cmd.params if p.name == "extras.[b]+"])
# expected: the same help twice
# actual:
# populate_command ["Append element(s) to the list at 'extras.\\[b]'."]
# setup_completion ["Append element(s) to the list at 'extras.[b]'."]
```
