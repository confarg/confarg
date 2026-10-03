# REF-54 — Two span loops in `dictexpr` that one helper writes

**Where:** `src/confarg/dictexpr/_expressions.py` (`_map_expressions`, `_resolve_single`) ·
**Filed:** 2026-09-24
**Effort:** S · **Risk:** low · **Impact:** none

`_map_expressions` and the interpolation branch of `_resolve_single` are the same loop: walk the
spans `_find_expressions` yields, append the text before each and a replacement for it, join.
They differ only in the replacement. `_map_expressions` keeps an escape as written and rewrites a
body with `fn`; `_resolve_single` unescapes (`$${x}` → `${x}`) and writes the evaluated value. One
helper taking the replacement as a `Callable[[_ExpressionSpan], str]` writes both. The
pure-expression fast path of `_resolve_single` stays: it returns a *typed* value, not a string.

Filed as two `re.sub` rewrites, when the regex `_EXPR_RE` delimited expressions. It cut a body
at its first `}`, and `_find_expressions`, the lexical scanner that replaced it
([expressions/values-and-references.md#delimiting-an-expression](../../architecture/expressions/values-and-references.md#delimiting-an-expression)),
has no `sub`. A third bullet, `_line_starts` as a prefix sum, went with BUG-139.

This sharpens one bullet of [REF-52](REF-52-mechanical-collapses-in-the-type-machinery.md),
which notes that `_resolve_single` and `_map_expressions` are the same accumulate loop differing
only in escape handling. REF-52 names the duplication; this names the answer. Close that half of
the bullet here.
