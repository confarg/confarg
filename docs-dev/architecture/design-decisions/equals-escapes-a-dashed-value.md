# The `=` form is the escape for a dashed value

`--key=--value` sets `key` to `--value` in all five front-ends; `--key --value` is
`Missing value for '--key'` in all four. A value that starts with `--` is indistinguishable
from a flag by shape, so something other than shape has to decide, and the `=` is the only
thing the user can write that already says "this is the value of that flag"
([CLI parsing](../cli-parsing/token-consumption.md#token-consumption)). Vanilla used to lose that information by
splitting `--key=--value` into two bare tokens before any flag-check ran
(BUG-27, closed); the dict-subkey and append spellings
(`--d.x=--v`, `--tags+=--a`) go through the same scan and so were broken in every front-end,
adapters included.

Rejected: **binding a dashed token in the space form** when exactly one value is expected.
click does this, and it is the outlier — argparse, cyclopts, `getopt` and jsonargparse all
refuse. Adopting it would have replaced a gap where vanilla stood alone against three
adapters with a gap where vanilla and click stood against two, and it makes a mistyped
`--key --verbose true` swallow `--verbose` as a value instead of erroring.

Rejected: **a bare `--` end-of-options separator**. No adapter can offer one — the host
framework tokenizes argv before confarg is called — so it would be a vanilla-only spelling,
and the environment has no equivalent at all. Filed as
[FEAT-17](../../todo/features/FEAT-17-end-of-options-separator.md) rather than decided here
([limitations](../limitations.md#cli-front-ends)).
