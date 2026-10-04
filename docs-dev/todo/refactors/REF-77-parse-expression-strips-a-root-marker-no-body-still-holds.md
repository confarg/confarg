# REF-77 — `_parse_expression` strips a root marker that no body reaching it still holds

**Where:** `src/confarg/dictexpr/_expressions.py` (`_parse_expression`, `_strip_anchor`) ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** low · **Impact:** none

`_parse_expression` runs `_strip_anchor` on every body, and its docstring and `_strip_anchor`'s
say this is what lets `build()` and `resolve()` accept `${::x}`. It is not: `resolve_expressions`
swaps every marker for a stand-in name (`name_anchors`) before any parse, and `_validate_ast` and
`_parse_anchored`, its only callers, see named bodies only, in which `_anchor_markers` finds
nothing. The strip is a tokenizer pass per cached parse that does nothing, and the docstrings
point a reader at the wrong mechanism
([reference-anchoring.md#reference-anchoring](../../architecture/expressions/reference-anchoring.md#reference-anchoring)).
Dropping it leaves the whole suite green, checked by hand on 2026-10-03.

Fix direction: parse the body as given, leave `_strip_anchor` to `canonicalize_references`, its
one real caller, and correct both docstrings.
