# FEAT-12 — Carefully scoped expression expansion

**Where:** `src/confarg/dictexpr/_expressions.py` (`_ALLOWED_NODES`, the call whitelist) ·
**Filed:** 2026-09-12
**Effort:** L *(list literals alone; XL with dict and set literals)* · **Risk:** high · **Impact:** behavior

The safety model forbids list/dict/set literals, slices, comprehensions, lambdas, f-strings
and `}` inside an expression
([07-expressions.md#safety-model](../../architecture/07-expressions.md#safety-model)). That is a
sound default, but it leaves expressions unable to say ordinary things —
`${[host, backup_host]}`, `${list(hosts) + [fallback]}`, `${sorted(ports)}`. A conservative
expansion — list and dict literals plus a fixed set of builtin conversions (`list`, `tuple`,
`dict`, `set`, `sorted`, `sum`, `any`, `all`) added to the existing free-function whitelist —
would meaningfully increase expression power **without touching `eval`**: the interpreter
still walks a whitelisted AST, and each new node has a small, total evaluation rule.

The coupling is explicit and decides the order of work. `_Prefixer` rewrites only `ast.Name`
bases, and that is correct *only* because no binding construct is whitelisted, so every
non-function `Name` is a reference base; **adding a binding construct — a comprehension or a
lambda — breaks reference prefixing** and requires reworking `_Prefixer` to carry a scope
([07-expressions.md#reference-anchoring](../../architecture/07-expressions.md#reference-anchoring),
[09-invariants.md#fragile-couplings](../../architecture/09-invariants.md#fragile-couplings)). List
literals bind nothing, so they are the safer first step and can land on their own. Two further
constraints: dict and set literals need `}` inside the expression, which the `${...}` regex
forbids, so they additionally require brace-balanced or lexical delimiter scanning — another
reason lists come first; and `sorted(key=...)` is off the table for as long as lambdas are,
so the added builtins take no callable arguments.

**Slices are already spoken for in part.** `::` is the configuration-root marker, and the rule
that keeps both readings available is that it is a marker only when the innermost enclosing
bracket is not `[`; inside a subscript it is a slice step, and `items[(::step)]` is how a root
lookup is spelled there ([07-expressions.md#implementation-constraints](../../architecture/07-expressions.md#implementation-constraints)).
Adding `ast.Slice` to the whitelist therefore needs no lexer change, but it does need tests
pinning `items[::2]`, `items[:3]` and `items[(::step)]` apart.

Parity is not at risk — the engine is shared by all three channels and all four front-ends, so
an expansion lands everywhere at once — but each new node must stay inside the deferral rule
([07-expressions.md#deferral-rule](../../architecture/07-expressions.md#deferral-rule)): a value
gate must still defer on `contains_expression`, and a literal that now resolves to a `list`
must reach `build()` as a list rather than being coerced early. Shell quoting of `[`/`]` is a
documentation matter, not a divergence.

Precedents: Bicep and CUE allow literals and a curated standard library with no general
evaluation; Jsonnet and Nix go all the way to a full functional language; Home Assistant and
Ansible hand config templating to Jinja2 and accept arbitrary-expression risk; OmegaConf
(Hydra) stays at interpolation plus registered resolver functions, closest to where confarg
is now. The curated-literals-and-builtins point is the Bicep/CUE end, reachable without
adopting a language.
