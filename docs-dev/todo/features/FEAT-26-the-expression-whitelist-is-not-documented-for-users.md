# FEAT-26 — The expression whitelist is not documented for users

**Where:** `README.md` (§ Expressions and variable interpolation), `examples/21_expressions/README.md`,
`docs/how-to/derived-values.md` ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** low · **Impact:** none

No user-facing page says what a `${...}` may contain. The README and Tutorial 21 show `int(...)`
and arithmetic, and the derived-values how-to says `len` "is part of the expression whitelist",
but the whitelist itself appears nowhere: not the free functions (`abs min max round ceil floor
str int float bool len`), not the string methods (`upper lower strip split replace startswith
endswith join`), not that a method runs only on a string (BUG-122), that keyword arguments,
list or dict literals, slices and comprehensions are refused, nor that a function name is a
function only when called (BUG-120). A user learns each of these from an
`UnsafeExpressionError`. The content exists, for maintainers, in
[safety-model.md](../../architecture/expressions/safety-model.md#safety-model); a short
reference table belongs in the README's expressions section or in Tutorial 21.

Precedents: Jinja2, CEL and simpleeval each document their callable set in their user docs.

The path spelling is just as undocumented: no user page shows a subscript (`${svc['web-1']}`,
`${servers[0].host}`, `${::['web-1']}`), though it is the only way to read a key that is no
identifier, and the `UnsafeExpressionError` for a name Python would normalize (`${ﬁle}`,
BUG-132) points the user at it
([values-and-references.md#spelling-a-path](../../architecture/expressions/values-and-references.md#spelling-a-path)).
