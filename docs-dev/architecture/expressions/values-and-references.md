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
An anchor marker takes either spelling too, so `${.['web-1']}`, `${.[0]}` and `${::['web-1']}`
read a sibling key, a sibling element and a root key
([reference anchoring](reference-anchoring.md#implementation-constraints)).

**A name reads the key it is written as, or is refused** (BUG-132). Python NFKC-normalizes every
identifier it parses (PEP 3131), so `${ﬁle}` (with the `ﬁ` ligature) or `${svc.ﬁle}` would read
the key `file`, silently, even when the configuration holds both; a string is never normalized,
so `${::['ﬁle']}` and `${svc['ﬁle']}` read the key as written. `_parse_expression` therefore
refuses a body that writes a name Python would read as another, as a body that does not parse:
reference extraction skips it, mounting leaves it as written (it would otherwise unparse `ﬁle`
as `file`), and validation reports it, naming both spellings and the subscript. The rule covers
every name, a callee (`ｍax(...)`) or a method (`.ｕpper()`) included, since the tokenizer sees
them all the same way. `_reads_as_written` is its one predicate, and the converse already asks it:
`_path_to_ast` never spells such a segment with a dot.

Rejected: **read the name as written**, recovering each identifier's token text after parsing.
JavaScript compares identifiers as written and JSONPath (RFC 9535) compares member names by code
point, with no normalization, so `${ﬁle}` would read `ﬁle` there. But the expression language
would stop being Python exactly where a reader cannot see it: `ｍax(a, b)` would name no
function, and every node carrying a name, a dot's included, would need its token found again
by offset. A refusal changes no answer Python gives, only declines one. jq makes the same call
from the other side: its bare identifiers are ASCII, so any other key takes `.["ﬁle"]`.

`_expressions._attribute_chain` is the one answer to "which config path does this node read?".
Reference collection asks it for the dependency graph and evaluation asks it for the value, so a
spelling can never be a dependency on one path and read another. `_expressions._path_to_ast` is
the converse, "which expression reads this path?": a dot where the segment is a name, a constant
subscript elsewhere, and a first segment that is no name off the root marker (`::['web-1']`). It
spells the prefix of a mounted file and the path a dot run stands for
([reference anchoring](reference-anchoring.md#a-document-is-prefixed-once-by-its-whole-mount-path)).

A computed subscript (`${svc[k]}`) spells no path to the dependency graph: its key is only known
once `k` is evaluated, so it is no dependency beyond the names it is computed from. Evaluation
knows the key, and reads it as the segment its constant spelling would be (`_key_segment`): a
string is the key, an integer the list index, so with `k: web`, `${svc[k]}` is `${svc['web']}`
— the same value, the same `Field 'svc.nope' not found` when it misses, the same
`index 5 out of range`. Evaluation asks `_attribute_chain` with its namespace, and the
dependency graph without, so the two differ only in what syntax alone cannot know. A key that
spells no segment (a bool, a float) is Python's subscript alone.

Evaluation reads the path first and falls back on Python's subscript only when the path is
missing (`_eval_path_or`): that is what lets `${name[0]}` index a string, and keeps a dict with a
non-string key (`{0: x}`, which YAML can produce) reachable as `${m[0]}`. A dot falls back the
same way, as the subscript of the name it spells, so `${svc[k].host}` reads what
`${svc[k]['host']}` reads; it never reaches a Python attribute
([safety model](safety-model.md#a-dot-reads-a-key-never-an-attribute)). The path model's segments
are strings, as everywhere else in `dictexpr`, so `${m[0]}` reads a key `"0"` before an integer
key `0`. When the fallback fails too, the path's own miss is reported — `Field 'svc.nope' not
found`, or `index 5 out of range` — rather than a `KeyError`.

The callee of a method call is no path at all: `${name.upper()}` evaluates `name` and calls the
method on it, never reading a key `name.upper`
([safety model](safety-model.md#a-method-is-a-string-method)).

Rejected: **runtime subscript first, path second.** `${m[0]}` would then mean the integer key
while the dependency graph, which only sees syntax, recorded the path `m.0` — two answers to one
spelling. Path-first is also the order an attribute already used.

Rejected, for a computed key (BUG-128): **Python's subscript first, the path only to word its
miss.** Before BUG-128 `${svc[k]}` was Python's subscript alone and its miss surfaced as an
`ExpressionEvalError` quoting the bare `KeyError` (`'nope'`), so the error a caller caught
depended on how the key was spelled. Keeping that order and naming the path only on a miss
would still give one segment two answers: with `k: 0`, `${m[k]}` read the integer key of
`{"0": a, 0: b}` while `${m[0]}` reads the string one, and `${xs[k]}` with `k: "1"` failed on
an element `${xs['1']}` reads — a miss reported as `Field 'xs.1' not found` on a path that
exists. Precedents give a key one meaning however it is written: jq's `.[$k]` is `.["web"]`
once `$k` is `"web"`, JavaScript's `a[k]` is `a["web"]`, and Jinja2's `StrictUndefined` raises
the same `UndefinedError` for `foo[k]` as for `foo.bar`.

## A position is a sequence of segments

Inside resolution a position — where an expression sits, what a reference reads, how far a dot
run climbs — is a tuple of segments (`_Path`), never a dotted string. The scan names each
expression by one, the dependency graph keys its nodes by them, `_anchor_prefix` drops segments
from one, and the write-back walks one with `_step`, the walk evaluation reads with. The file
loader holds a node's position within its file the same way, for the clamp on dot runs
([reference anchoring](reference-anchoring.md#dots-are-clamped-at-the-file-root)). A key
holding a dot (`example.com`, which every format can spell as a quoted key) is then one segment
like any other: `{"a.b": …}` and `{"a": {"b": …}}` are `("a.b",)` and `("a", "b")`, two nodes
that cannot collide. Joining to a dotted string and splitting it again made them one node, wrote
a result back to the wrong key, and climbed one level too many from inside such a key (BUG-124).

The dotted form survives only in messages, `Field 'a.b' not found`, which a person reads and
nothing parses back. Precedents keep paths structured for the same reason: jq's `path()`,
`getpath` and `setpath` work on arrays of keys (`["a.b"]`), and JSON Pointer (RFC 6901)
escapes its separator inside a segment rather than let a key hold it.

## Referencing a whole subtree

A reference is a path, not a leaf selector: `_get_nested` returns whatever sits at that path,
so `${db}` is as valid as `${db.port}` and substitutes the entire node — dict, list or scalar.
Every expression inside the node resolves first, so what is substituted holds no `${...}`; a
node that holds the referencing expression itself is therefore a cycle
([resolution](resolution.md#a-reference-reads-everything-its-path-reaches)).

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
