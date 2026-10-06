---
filed: 2026-09-24
where:
  - src/confarg/dictexpr/_expressions.py::_map_expressions
  - src/confarg/dictexpr/_expressions.py::_resolve_single
effort: S
risk: low
impact: none
severity: trivial
---
# REF-54 — Two span loops in `dictexpr` that one helper writes

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

This was half of a REF-52 bullet, which noted that `_resolve_single` and `_map_expressions` are
the same accumulate loop differing only in escape handling. REF-52 closed without it. The other
half, folding `_strip_anchor` into `_name_anchor`, was declined
([look-alike code that behaves differently stays apart](../../architecture/design-decisions/look-alike-code-that-behaves-differently-stays-apart.md#look-alike-code-that-behaves-differently-stays-apart)).
This loop is not that case: the two copies differ only in the replacement, which one
`Callable` parameter carries.
