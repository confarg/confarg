# Token model

- `_StrToken` (a `str` subclass) marks **untyped text from a channel that carries no types**:
  CLI, environment, CSV/TSV cells. Only tokens are coerced from text. A plain `str` came from
  a self-describing file and is never re-interpreted, so YAML's `"yes"` stays a string (no
  "Norway problem" for files).
- `_UnionSeqToken` (a `_StrToken`) marks a lone CLI token for a scalar+sequence union; it
  alone may fall back to a one-element list ([CLI parsing](../cli-parsing/token-consumption.md#unions-with-sequence-variants)).
- `_Pinned(tp, value)` carries an explicitly cast value through the merge dict; `construct`
  honors it before anything else, including `None` handling.
- Tokens must never leak out: error messages print them as `str` (`_src_type`, which lives in
  `_types.py` beside `_StrToken` rather than in `typedload/`, so every module that formats a
  channel value can reach it without importing an engine — BUG-57 was the fifth site to print
  `type(value).__name__` instead), the dump path
  unwraps them in `_serialize_leaf` with `isinstance(v, _StrToken)`, and `dictexpr._map_strings`
  preserves the subclass when rewriting expressions. The test is `isinstance`, not an exact
  type test, so it covers the whole token hierarchy — `_UnionSeqToken` included, and any token
  type added later. Other `str` subclasses stay untouched all the same: `_StrToken` is private,
  so nothing a caller writes — a registered `str` leaf type included — can inherit from it, and
  the registry loop below the unwrap stays reachable for it.
