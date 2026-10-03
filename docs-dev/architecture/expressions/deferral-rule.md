# Deferral rule

An expression's value is unknown until `build()`, so it can never be proven wrong earlier.
**Every value gate that runs before `build()` must defer expression tokens, and must decide
that with `dictexpr.contains_expression(value)`** — never by testing for `${` itself. The
predicate matches both `${...}` and the escape `$${...}` (resolution rewrites both).

Gates wired to it:

| Gate | Where |
|---|---|
| eager leaf coercion (CLI + env, all front-ends) | `typedload._coerce._try_coerce` |
| argparse choices | `_ExpressionTolerantChoices.__contains__` |
| click choices | `_ExpressionTolerantChoice.convert` |
| cyclopts `Literal` | `_expression_tolerant_convert` |
| locals override coercion | `_pipeline._coerce_override` |

Why a rule and not a side effect of failing coercion: a registered leaf may *succeed* on the
raw text (`Path("${base}/logs")`), turning the expression into a non-`str` value that
resolution (which only scans strings) never revisits — silently producing a literal path.

A gate that skips this check rejects on one channel what the others accept, which is the
cross-channel divergence [invariants](../invariants.md#cross-channel-parity) forbids. `build()`
validates the resolved result, so an expression landing outside a `Literal` still fails,
identically everywhere.
