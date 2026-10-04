# A lint rule is enabled, not hand-fixed once

When lint names a pattern worth banning, the rule is enabled in `.ruff.toml` and the live sites are fixed — a hand fix without the rule
means the pattern comes back. The two rules so far are preview rules in the pinned ruff (0.15.16):
`FURB118` (reimplemented-operator — `lambda ec: ec[0]` is `operator.itemgetter`) and `PLW0717`
(too-many-statements-in-try-clause — what would catch the multi-statement `try` bodies
[REF-53](../../todo/refactors/) closed coming back). Preview mode is scoped to `[lint]` and paired
with `explicit-preview-rules = true`, the setting ruff ships for exactly this narrow opt-in:
every other preview rule stays off. Enabling preview wholesale was measured and rejected: at
ruff 0.15.16 this tree reports 2897 errors under full preview, against 4 under the two rules.

Cost: a deliberate oversized `try` is now a lint error. The wholesale best-effort blocks —
`cli/_build.py`'s dynamic-flag scan and the two completion extenders, whose whole point is that
any failure degrades silently
([invariants § Fragile couplings](../invariants.md#fragile-couplings)) — carry a permanent
`# noqa: PLW0717` with their reason on the `try` line, as does `tests/test_callables.py`'s
`_add`, whose point is to be a user-defined function with its own dotted path rather than
`operator.add`. The noqa is the marker that the deviation is a decision, not an oversight; a
`try` body that grows statements without one fails lint.
