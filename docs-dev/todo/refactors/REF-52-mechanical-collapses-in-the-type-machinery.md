# REF-52 — Mechanical collapses in the type machinery

**Where:** `src/confarg/_types.py`, `src/confarg/typedload/_coerce.py`,
`src/confarg/typedload/_construct.py`, `src/confarg/_callable.py`, `src/confarg/_import.py`,
`src/confarg/dictexpr/_expressions.py` · **Filed:** 2026-09-24
**Effort:** S · **Risk:** low · **Impact:** none

Independent, individually small, all verified; roughly 50 source lines and 15 test lines. Grouped
because each is a one-site edit with no design question attached — split them across revisions if
any turns out to be bigger than it looks.

- `_types.py` spends **27 lines importing nine names** from `collections.abc`, an artifact of
  isort not combining aliased imports. Dropping the `…ABC` aliases, or setting
  `combine-as-imports` in [`.ruff.toml`](../../../.ruff.toml), makes it one statement.
- `_coerce`'s `_coerce_bool_value` / `_coerce_int_value` / `_coerce_float_value` /
  `_coerce_str_value` share one shape — native-type passthrough, `_StrToken` parse, raise
  `cannot_coerce` — and can be driven from `_SCALAR_COERCIONS` extended to carry the native types
  and the parse function. **`int` must keep its base-0 parse**; base 10 would change what `"0x10"`
  and `"010"` mean.
- `_construct._struct_matches_value` is `_structurally_matches` plus a dict guard, the last four
  lines verbatim identical.
- Three byte-identical try-each-variant-then-no-match loops in `_construct.py` want one
  `_first_constructible`.
- `_construct._try_pinned_dict` re-derives the cast-name-to-type map by scanning
  `_LEAF_COERCIONS` for `__name__` matches, while `_cast.cast_name_for_type` already owns the
  forward direction. A `type_for_cast_name()` in `_cast.py` puts both directions in one place; no
  import cycle, since `_coerce` does not import `_cast`.
- Three hand-rolled attribute-chain walks (`_import.py` twice, `_callable.py` once) are
  `functools.reduce(getattr, parts, module)`.
- `_callable.py` spells "the parameters a caller can fill" three different ways, and
  `_format_fn_dict_example` runs the same comprehension twice, the two copies differing only by
  `p.default is empty` versus `is not empty` — one helper with a `required` flag serves all four.
  Its `(path, union_tag, construct_fn)` triple, threaded through ten functions and carrying three
  of the file's lint suppressions, wants the frozen-context pattern the file already uses for
  `_ClassSpec`.
- **Verified dead:** `_types._is_collection` and `_types._callable_return_type` have zero
  production callers — only `tests/test_coverage_gaps.py` and `tests/test_callables.py` — and
  `_callable.py` documents deliberately *not* using the latter, because `Callable[..., None]`
  reports `None` and it cannot tell that from bare `Callable`. Delete both with their tests.
- **Verified unreachable:** three `op_func is None` branches and one fallthrough in the dictexpr
  evaluator. `_validate_ast` rejects any node type outside `_ALLOWED_NODES`, which is exactly the
  union of the three operator-map key sets, so no public path reaches them. They survive only
  because a coverage test calls `_evaluate_ast` directly, bypassing validation — worth naming as a
  pattern, since a test written to cover a branch is now what keeps the branch alive.
- `dictexpr`'s `_strip_anchor` / `_name_anchor` / `_unname_anchor` are three
  `_replace_spans(_anchor_markers(...))` rewrites differing only in the per-level replacement;
  `_resolve_single` and `_map_expressions` are the same `finditer` accumulate loop differing only
  in escape handling.

Not in scope, and deliberately so: the bracket tracking in `_anchor_markers` looks like it guards
an unreachable feature, because `ast.Slice` is not whitelisted and `${items[::2]}` raises
`UnsafeExpressionError` today. It is reserved for
[FEAT-12](../features/FEAT-12-scoped-expression-expansion.md) on purpose. If anything is wrong
there it is the present tense of the docstring, not the code.
