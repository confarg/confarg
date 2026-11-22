---
filed: 2026-11-12
where:
  - src/confarg/_parse_cli.py::_config_pairs_in  # refuses a bare --config while reading the pairs, before the loop
  - src/confarg/_api.py::_merge  # runs that pre-scan ahead of the loop
  - src/confarg/cli/cyclopts/_context.py::_merge_app  # the config scan, then refuse_bare_occurrences: two passes, not argv order
effort: M
risk: medium  # no test spells two bare refusals in one argv
impact: behavior
severity: minor  # close call with trivial: both messages are true, only which flag the refusal names differs
introduced_by: [BUG-51, BUG-233, BUG-236, BUG-110, BUG-114]  # cyclopts since BUG-51 (PR-222); vanilla since PR-447, which closed the other four
---

# BUG-333 — A bare config flag is refused before an earlier bare flag on vanilla and cyclopts

[A flag that stands bare](../../architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare) answers refused bare flags in argv order, "the order vanilla's loop refuses in".
That holds for one refusal.
With two in one argv, the front-ends disagree:

- vanilla and cyclopts refuse a bare `--config` first, wherever it sits;
- argparse refuses whichever comes first, since its actions run in argv order.

So `--pair --config` on a `tuple[int, int]` field names `--config` on vanilla and cyclopts and `--pair` on argparse.
All three raise `ConfargError`, and only the message differs.
click and typer answer with their own usage error here ([BUG-96](BUG-96-a-bare-scalar-flag-exits-with-the-frameworks-own-error-on-the-adapters.md)).

Vanilla reads the `--config` pairs before its loop on purpose, because the files they mount type the flags below a node they name.
`_config_pairs_in` refuses a bare occurrence while reading them, so that refusal comes ahead of every refusal the loop would raise earlier in argv.
cyclopts runs the same scan as a pre-parse refusal, and only then `refuse_bare_occurrences`.

Fix direction: refuse in argv order on both:

- the vanilla pre-scan leaves a bare config occurrence for the loop to refuse where it stands;
- cyclopts makes its two pre-parse refusals one argv-order pass, for example by building its refusal map off `FlagSpec.bare_refusal()`, which the config specs already answer.

Origin: two revisions, each a fix.

- BUG-51 (PR-222) gave cyclopts its pre-parse `--config` refusal.
  That was needed because cyclopts asserted on a bare `nargs="*"` flag.
  From then on cyclopts refused the config flag first, while vanilla and argparse still answered `--pair` (checked by running this reproduction at PR-222 and at its parent).
  BUG-74 (PR-251) later added `refuse_bare_occurrences` after that scan and kept the order.
- PR-447 (BUG-233, BUG-236, BUG-110, BUG-114) moved vanilla's config-pair scan ahead of its loop, so that the mounted files type the flags.
  Since then vanilla answers `--config` too, while argparse, which BUG-63 (PR-393) made refuse in argv order, kept naming `--pair` (checked at PR-447 and at its parent).

The rule both should keep is BUG-63's, so this is a regression that two fixes produced as a side effect, not a question.

```python
from dataclasses import dataclass

import cyclopts

import confarg
from confarg.cli.argparse import make_parser, merge_namespace
from confarg.cli.cyclopts import merge_app, populate_app


@dataclass
class T:
    pair: tuple[int, int] = (0, 0)


argv = ["--pair", "--config"]
try:
    confarg.merge(T, argv=argv, env={})
except confarg.exceptions.ConfargError as e:
    print("vanilla :", e)
try:
    merge_namespace(T, make_parser(T, argv=argv).parse_args(argv), argv=argv, env={})
except confarg.exceptions.ConfargError as e:
    print("argparse:", e)
app = cyclopts.App(name="demo")
populate_app(T, app, argv=argv)
try:
    merge_app(T, app, argv=argv, env={})
except confarg.exceptions.ConfargError as e:
    print("cyclopts:", e)

# expected (argv order, all three):
#   Missing value for '--pair'. Usage: --pair <value> <value>
# actual:
#   vanilla : Missing file path after --config. Usage: --config /path/to/config.yaml
#   argparse: Missing value for '--pair'. Usage: --pair <value> <value>
#   cyclopts: Missing file path after --config. Usage: --config /path/to/config.yaml
```
