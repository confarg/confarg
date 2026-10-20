---
filed: 2026-10-20
where:
  - src/confarg/cli/argparse/_register.py::make_parser
  - src/confarg/_defaults.py::_resolve_options
effort: S
risk: low
impact: none
severity: trivial
---

# REF-102 — `make_parser` tells a merge option from a parser keyword by its own test

"Is this keyword a merge option?" is `_defaults._resolve_options` in the [canonical table](../../architecture/invariants.md#delegate-to-the-canonical-function), which tests `key in MergeOptions.__optional_keys__` ([one option set](../../architecture/pipeline/api-seams.md#one-option-set)).
`make_parser`, which splits its `**kwargs` between `populate_parser` and `argparse.ArgumentParser`, tests `key in MergeOptions.__annotations__` instead.
The two sets agree today; they part the day `MergeOptions` gains a required key, a `ClassVar` or a base class, and then a keyword lands on the wrong side with no error from either.

Fix direction: `_defaults` exposes the one predicate (`is_merge_option(key)`, or the frozenset itself) and both `_resolve_options` and `make_parser` ask it.
