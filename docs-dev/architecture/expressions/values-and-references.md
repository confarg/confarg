# Values and references

## Value typing

A string that is exactly one `${expr}` keeps the expression's Python type (int, list, …).
Anything with surrounding text, including surrounding whitespace, is string interpolation.
`$${...}` is an escape producing the literal `${...}`.

Whitespace *inside* the braces is layout: `${ a }` is `${a}`, as `{ a }` is in an f-string and
`" a "` is to `eval()`. Every parse goes through `_parse_body`, which strips it, because
`ast.parse` alone reads a leading blank as an indent.

## Delimiting an expression

An expression ends at the first `}` that is neither inside a string literal nor closing a brace
the body opened itself, so `${root + "{city}/{city}_{idx}.png"}` is one expression. That is the
rule every host of embedded expressions applies: Python's f-string replacement fields (the
hand-written scanner CPython used before 3.12, then the tokenizer of PEP 701), ECMAScript
template literals, and OmegaConf, whose 2.1 interpolation grammar replaced a regex. The
old `\$\{([^}]+)\}` regex ended at any `}`, which cut a `str.format`-style template in half.

`_find_expressions` is the one place that answers "where are the expressions in this string?":
the predicate, the scan, validation, evaluation, prefixing and the anchor-depth check all iterate
its spans, so no two of them can disagree on where an expression stops.

- **A dedicated scanner, not `tokenize`.** Delimiting only has to know where a string literal
  ends: on its opening quote, single or triple, with a backslash escaping the next character
  whatever the prefix (`r'\''` is one literal). Python's tokenizer knows that too, but it
  tokenizes every other character as well, so where a malformed body ends would hang on how
  a given Python version's tokenizer fails (pure Python up to 3.11, C since 3.12) instead of
  the body reaching `ast.parse` and being reported with its text. This is the CPython
  pre-3.12 f-string design.
- **Escapes are delimited the same way**, so `$${a + '}'}` unescapes to `${a + '}'}`.
- **An unclosed body is literal text**, as it was under the regex: a `${` with no closing
  brace, or one whose string literal never closes (`${'a}`), is not an expression and passes
  through unchanged. f-strings and template literals reject it instead; confarg keeps treating
  a stray `${` in a value as text, as it always has.
- An f-string *inside* an expression is scanned as an ordinary literal, which PEP 701's nested
  same-quote form (`f'{'a'}'`) defeats. That is moot: f-strings are outside the whitelist
  ([safety model](safety-model.md#safety-model)), and the mis-delimited body still fails to
  parse or to validate.

## Spelling a path

A dot and a constant subscript each spell one path segment: `${svc.web.host}`,
`${svc['web']['host']}` and `${svc["web"].host}` read the same key and are the same dependency.
An integer subscript is a list index, `${servers[0].host}` or `${servers[-1].host}`. The
subscript is the only way to write a key that is no identifier: `${svc['web-1'].port}`,
`${hosts['example.com']}`. Precedents agree: in JavaScript `a.b` is `a['b']`, in jq `.foo` is
shorthand for `.["foo"]`, and Jinja2 documents `foo.bar` and `foo['bar']` as the same lookup.

`_expressions._attribute_chain` is the one answer to "which config path does this node read?".
Reference collection asks it for the dependency graph and evaluation asks it for the value, so a
spelling can never be a dependency on one path and read another. A computed subscript
(`${svc[k]}`) spells no path: its key is only known once `k` is evaluated, so it is Python's own
subscript, and it is no dependency beyond the names it is computed from.

Evaluation reads the path first and falls back on Python's access only when the path is missing
(`_eval_path_or`): that is what lets `${name.upper()}` call a method and `${name[0]}` index a
string, and keeps a dict with a non-string key (`{0: x}`, which YAML can produce) reachable as
`${m[0]}`. The path model's segments are strings, as everywhere else in `dictexpr`, so `${m[0]}`
reads a key `"0"` before an integer key `0`. When the fallback fails too, the path's own miss is
reported — `Field 'svc.nope' not found`, or `index 5 out of range` — rather than a `KeyError` or
an `AttributeError` on `dict`.

Rejected: **runtime subscript first, path second.** `${m[0]}` would then mean the integer key
while the dependency graph, which only sees syntax, recorded the path `m.0` — two answers to one
spelling. Path-first is also the order an attribute already used.

## Referencing a whole subtree

A reference is a path, not a leaf selector: `_get_nested` returns whatever sits at that path,
so `${db}` is as valid as `${db.port}` and substitutes the entire node — dict, list or scalar.

**Value semantics, not identity.** Resolution finishes before construction begins
([pipeline](../pipeline/stages.md#the-pipeline)), so what a site references is raw data, never
an object. Construction then walks the resolved dict with no memo keyed by node identity, and
two sites referencing one node yield two objects that are equal and not identical. confarg
builds a value, not an object graph: sharing one instance between two fields is a
dependency-injection concern and stays out of scope, which is the same boundary that keeps the
library free of a container ([design decisions](../design-decisions/no-custom-types-required.md#no-custom-types-required)).

**The substituted node is the live sub-dict, not a copy.** `_get_nested` hands back the node
itself, so after `resolve()` the referencing path and the referenced path are one dict.
`build()` hides that — it constructs from the dict and drops it — but the three-step seam
([pipeline](../pipeline/api-seams.md#public-api-seams)) exposes it: mutating `resolved["db"]` in
place also mutates every path that referenced it. Copying on substitution would pay a deep copy
per reference to protect a caller the seam does not invite (its documented use is to inspect and
dump), so the aliasing stands as a limitation ([limitations](../limitations.md#expressions)) rather than a
defect.

**The union tag travels with the node.** A referenced struct carries its `class` key along, and
`_construct_struct_dispatch` honors a tag even on a non-union field
([types](../types/construction.md#union-construction)). The referencing field's *declared* type
therefore governs what is built: annotated with the tagged class it constructs, annotated with a
leaf type it is a coercion error — `${db.port}` is the reference for a single field.
