---
filed: 2026-10-11
where:
  - src/confarg/cli/_build.py::build_static_flags  # the root --config help
  - src/confarg/cli/_build.py::_build_union_tag_spec
  - src/confarg/cli/cyclopts/_register.py
effort: S
risk: medium
impact: behavior
severity: minor  # a wrong help line on one front-end
introduced_by: [PR-26]  # the cyclopts adapter handed confarg's help strings to cyclopts unchanged
---
# BUG-226 — cyclopts `--help` drops the `<field>` placeholder from confarg's help text

Two help strings confarg writes spell a placeholder in angle brackets: the root `--config` flag's (`Use --config.<field> FILE to scope…`) and a union field's tag flag (`Once set, use --pet.<field> flags…`). cyclopts renders parameter help as Markdown by default (`DEFAULT_FORMAT = "markdown"` in cyclopts 4.24.0), which reads `<field>` as an HTML tag and drops it, so the reader is told `Use --config. FILE`. argparse, click and typer print the text as written; a cyclopts app with `help_format="plaintext"` does too.

Fix direction: the help format is the host application's setting, so confarg's own strings should read the same under every format cyclopts offers (Markdown, reStructuredText, rich, plain) rather than override it — a placeholder without angle brackets (`--config.FIELD`) does. Check every help string `cli/_build.py` and `cli/_spec.py` write ([framework specifics](../../architecture/cli-adapters/framework-specifics.md#framework-specifics)).

Origin: latent since PR-26, which added the cyclopts adapter and registered the help strings the other adapters already used. That cyclopts 4.12, the version PR-26 locked, also defaulted to Markdown is *(inferred)*; 4.24.0 does. The placeholder itself dates from PR-5, when argparse was the only front-end.

```python
import contextlib
import io
from dataclasses import dataclass, field

import cyclopts

from confarg.cli.cyclopts import populate_app


@dataclass
class A:
    x: int = 0


@dataclass
class B:
    y: int = 0


@dataclass
class App:
    pet: A | B = field(default_factory=A)


app = cyclopts.App(console=None)
populate_app(App, app, argv=[])
out = io.StringIO()
with contextlib.redirect_stdout(out), contextlib.suppress(SystemExit):
    app(["--help"], exit_on_error=False)
text = " ".join(" ".join(line.strip("│ ") for line in out.getvalue().splitlines()).split())
for needle in ("Use --config.", "use --pet."):
    start = text.index(needle)
    print(text[start : start + 40])

# expected: the placeholder is part of the help text, as on argparse, click and typer
#   Use --config.<field> FILE to scope a fil
#   use --pet.<field> flags for that class's
# actual:   cyclopts renders the help as Markdown, which drops `<field>` as an HTML tag
#   Use --config. FILE to scope a file's con
#   use --pet. flags for that class's fields
```
