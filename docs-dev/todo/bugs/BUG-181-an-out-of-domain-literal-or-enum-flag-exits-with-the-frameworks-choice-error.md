---
filed: 2026-10-06
where:
  - src/confarg/cli/argparse/_register.py
  - src/confarg/cli/click/_register.py
  - src/confarg/cli/typer/_register.py
  - src/confarg/cli/cyclopts/_register.py
effort: M
risk: medium
impact: behavior
severity: minor  # the value is invalid either way; only the error's type and text differ
introduced_by: [PR-5, PR-13, PR-26]  # argparse, click (typer through it) and cyclopts each handed the choices to their framework; each bisected
---
# BUG-181 — An out-of-domain Literal or Enum flag exits with the framework's choice error on the adapters

`--lit c` on `lit: Literal["a", "b"]` (or `--col purple` on an `Enum` field) is kept by vanilla's
`merge()`, and `load()` refuses it in `build()` with `TypeCoercionError`, as every front-end does
for the same value from the environment or a file. On the four adapters the framework's own
choice check refuses the CLI token first: argparse and the clicklike front-ends exit 2 and
cyclopts exits 1, before any confarg code runs. A caller catching `ConfargError` around `load()`
gets the error on vanilla and a process exit on the adapters, and an adapter's `merge_*` never
returns the dict `merge()` returns. That breaks
[adapter output equals vanilla output](../../architecture/invariants.md#adapter-output-equals-vanilla-output)
and [merge stays unvalidated](../../architecture/invariants.md#merge-stays-unvalidated). The
refusal is intended but not approved:
[expression-tolerant choice gates](../../architecture/cli-adapters/parity.md#expression-tolerant-choice-gates)
defers `${...}` tokens while "keeping native help, completion and error text for real values",
yet [cross-channel parity](../../architecture/invariants.md#cross-channel-parity) lists no such
divergence among the approved ones.

Fix direction: either widen the existing gates (`_ExpressionTolerantChoices`,
`_ExpressionTolerantChoice.convert`, `_expression_tolerant_convert`) to let every token through,
keeping `choices` for help and completion only, so `build()` judges the domain as it does for
the other channels; or approve the parse-time refusal as a divergence leaning to the frameworks'
idiom ([design decisions](../../architecture/design-decisions/divergence-leans-to-the-backend.md#a-divergence-leans-towards-the-affected-backends-own-idiom)).
BUG-96 is the same shape for a bare scalar flag.

Origin: latent since each adapter was written; vanilla's own parser has kept the token at every
revision below. Each was checked by running this reproduction, for `--lit c` and `--col purple`,
against the revision's own tree. The initial version (PR-5) gave argparse `choices` for a
`Literal` and an `Enum` (its member names): vanilla merges both, argparse exits 2. PR-13 did the
same with `click.Choice`, and typer, which PR-13 served through the click module, refused through
it too (run with typer 0.25.1, the oldest PR-13 allowed): both exit 2. PR-26 annotated the
cyclopts parameter with a `Literal` built from the same choices (`_make_literal`), which cyclopts
enforces by converting: it exits 1.

Later revisions kept the refusal on purpose rather than causing it. PR-46 widened an `Enum`'s
choices from its names to its names and values, so that `--color blue` was no longer refused, and
left a value outside both refused. PR-99 added the expression-tolerant gates and wrote in each
that a real out-of-domain value "still fails with" the framework's own error; PR-111 moved that
rationale into the parity note. PR-194 (BUG-7) rebuilt typer on the clicklike seam over
`TyperChoice`, which refuses the same way (checked: exits 2).

```python
from dataclasses import dataclass
from typing import Literal

import confarg
from confarg.cli.argparse import make_parser, merge_namespace


@dataclass
class Cfg:
    lit: Literal["a", "b"] = "a"


argv = ["--lit", "c"]
print(f"vanilla merge: {confarg.merge(Cfg, argv=argv, env={})!r}")
try:
    confarg.load(Cfg, argv=argv, env={})
except confarg.exceptions.ConfargError as e:
    print(f"vanilla load:  {type(e).__name__}: {e}")
ns = make_parser(Cfg, argv=argv).parse_args(argv)
print(f"argparse:      {merge_namespace(Cfg, ns, argv=argv, env={})!r}")

# expected:
#   vanilla merge: {'lit': 'c'}
#   vanilla load:  TypeCoercionError: Cannot coerce str 'c' to Literal('a', 'b') at 'lit'
#   argparse:      {'lit': 'c'}
# actual (click, typer exit 2 too; cyclopts exits 1):
#   vanilla merge: {'lit': 'c'}
#   vanilla load:  TypeCoercionError: Cannot coerce str 'c' to Literal('a', 'b') at 'lit'
#   <script>.py: error: argument --lit: invalid choice: 'c' (choose from a, b)   (argparse exits 2)
```
