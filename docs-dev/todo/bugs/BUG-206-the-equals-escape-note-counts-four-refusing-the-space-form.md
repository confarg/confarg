---
filed: 2026-10-07
where:
  - docs-dev/architecture/design-decisions/equals-escapes-a-dashed-value.md  # the "in all four" sentence
effort: S
risk: low
impact: none
severity: trivial
introduced_by: [BUG-53, BUG-54]  # PR-238, whose note counts four refusers where no partition of the five gives four
---
# BUG-206 — The `=` escape note counts four front-ends refusing the space form; all five do

The note says the `=` form delivers a dashed value "in all five front-ends" but the space form "is `Missing value for '--key'` in all four" ([equals-escapes-a-dashed-value.md](../../architecture/design-decisions/equals-escapes-a-dashed-value.md#the--form-is-the-escape-for-a-dashed-value)). All five front-ends refuse the space form today — vanilla, click and typer raise confarg's `Missing value for '--key'`, and argparse and cyclopts exit with the framework's own error — so no partition of the five gives four, and the exact message the sentence names is three front-ends wide. Fix direction: count five for the refusal and name the message split, or drop the count; the [cross-channel parity](../../architecture/invariants.md#cross-channel-parity) the sentence's first half already counts in five is the rule it leans on.

Origin: latent from the BUG-53/BUG-54 fix (PR-238, 2026-10-03), which wrote the five-vs-four contrast. One day later PR-274 (BUG-87, REF-72) rewrote the adapters' CLI channel as vanilla's loop over argv; before it, the clicklike front-ends read the channel off the parse result, where click and typer bound the dashed token to the flag, so the refusers were three — and after it they are five. No partition before or after gives four *(inferred: the pre-PR-274 count of three rests on the clicklike seam reading the parse result, not on a run at PR-238)*.

```console
$ grep -n "in all five front-ends\|in all four" docs-dev/architecture/design-decisions/equals-escapes-a-dashed-value.md
3:`--key=--value` sets `key` to `--value` in all five front-ends; `--key --value` is
4:`Missing value for '--key'` in all four. A value that starts with `--` is indistinguishable
$ # confarg.load(C, argv=["--key", "--value"], env={}) with one str field, per front-end:
vanilla: ConfargError: Missing value for '--key'. Usage: --key <value>
argparse: "error: argument --key: expected one argument", SystemExit(2)
click: ConfargError: Missing value for '--key'. Usage: --key <value>
typer: ConfargError: Missing value for '--key'. Usage: --key <value>
cyclopts: "Parameter --key requires an argument.", SystemExit(1)
# expected: the space form refused in all five front-ends, three with confarg's own message
# actual:   the note counts four
```
