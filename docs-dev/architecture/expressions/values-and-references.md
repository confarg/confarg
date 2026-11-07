# Values and references

## Value typing

A string that is exactly one `${expr}` keeps the expression's Python type (int, list, …).
Anything with surrounding text, including surrounding whitespace, is string interpolation.
`$${...}` is an escape producing the literal `${...}`.

A field default the target declares is a value a reference reads, laid below the data before resolution; a default string is laid escaped, so it reads as the text the class declared and is never evaluated ([design decisions](../design-decisions/a-field-default-is-the-base-layer.md#a-default-string-stays-text)).

Whitespace *inside* the braces is layout: `${ a }` is `${a}`, as `{ a }` is in an f-string and `" a "` is to `eval()`.
Every parse goes through `_parse_body`, which strips it, because `ast.parse` alone reads a leading blank as an indent.

## A typed leaf reads as its object

The merged dict holds an `Enum` or registered leaf as it was written, on every channel ([token model](../types/token-model.md#a-leaf-reaches-the-merged-dict-as-written)).
`build()` and `resolve()` hand `resolve_expressions` a reader and a writer, and an expression reads such a leaf as its object wherever one type is certain:

| Expression, `c: Color` (`RED = "red"`) set by `RED`, `red` or the default | Value |
|---|---|
| `${c}` into a `str` field, `"${c}@x"` | `'red'`, `'red@x'`: the dump form, never `str()` |
| `${c == other}`, `${lvl == 1}` on an `IntEnum` spelled `LOW` | `True` |
| `${p / 'sub'}`, `p: Path` | `Path('…/sub')`, left in the data as `'…/sub'` |
| `${svc[c]}`, `svc` keyed by `red` | the entry `red`: a computed key is spelled in its dump form |
| `${c == 'red'}` on a plain `Enum` | `False`: a member equals no text |

- **The reader** (`_typed_read.TypedReading`) steps from the root to the position read by the typed merge's own walk (`TypedAt`, which reads the tag or spec each node holds), and coerces the value there with `_coerce.read_as_object` where that type, an optional included, is one `Enum`, registered or `Literal`-over-`Enum` type, or a number, a bool or `None`: a file's `1` at a `float` reads `1.0`, as construction builds it (BUG-154).
  A union of several variants reads as the variant construction picks (`_construct.read_union_leaf`), every variant but a Callable tried: `str | Color` reads `red` as the member, `hello` as written, and `int | str` reads the token `5` as the number it builds.
  `Any` and a base with untagged subclasses read as written, as do a value the type refuses and a pending op's items.
  A dict whose class key names a registered leaf reads as the leaf construction builds from it, wherever construction takes the tag — at the leaf, a struct it subclasses, a union, an `Any` or a Callable — so `{class: pkg.Point, x: 3}` reads as `"3"` does (BUG-283); [a tagged leaf reads as the leaf it builds](#a-tagged-leaf-reads-as-the-leaf-it-builds) says where it does not.
  It applies to every read, a source's value, an earlier expression's result and each leaf of a subtree alike, so an expression never sees one leaf as text and another as the object.
- **Every value a read reaches has resolved.**
  The dependency graph orders before a read every expression it reaches ([a reference reads everything its path reaches](resolution.md#a-reference-reads-everything-its-path-reaches)), and a subscript indexes no base the graph did not order ([spelling a path](#spelling-a-path)), so text spelling `${...}` that a read meets is the literal an escape resolves to: `$${HOME}`, resolved to the literal `${HOME}`, reads as `Path('${HOME}')` at a `Path` field, as construction builds it, and so does the same text an expression computes (BUG-310).
  `contains_expression`, the predicate of every gate before `build()` ([deferral rule](deferral-rule.md#deferral-rule)), matches the literal as well as the expression, so it cannot tell them apart once resolution has started; until BUG-310 the reader asked it, and read every literal as text.
  BUG-310 told an expression yet to resolve by its position, from the set of positions resolution had still to write, because a subscript indexing its base read the base whole, pending expressions included; once that read reached its own position (BUG-311), no read met the set any more, and it went.
- **The writer** (`_serialize.written_form`) gives what an expression leaves behind — a pure result, an interpolated piece, a computed subscript key — in the form `dump()` writes: an `Enum` member's value, a registered type's serializer.
  `resolve()` rewrites only what expressions produced, so a source's `RED` comes out as `RED`.
- **Without them**, `resolve_expressions` reads and writes values as they are: the engine knows no type ([resolution](resolution.md#resolution-algorithm)).

Why objects inside and the dump form at the edges, and what was rejected: [design decisions](../design-decisions/an-expression-reads-a-typed-leaf-as-its-object.md#an-expression-reads-a-typed-leaf-as-its-object).

### A tagged leaf reads as the leaf it builds

[An explicit tag opts a leaf back in](../design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in): a dict whose class key names a registered leaf builds it from its fields.
The reader (`_typed_read._read_tagged_leaf`) reads such a dict as what `construct` builds at the position, before walking it as a struct's fields, so a reference reads the built value whichever spelling the leaf was written in:

| `origin: Point \| None`, `Point` registered and dumped as its `x` | `"at ${origin}"` | `other: Point = "${origin}"` | `a: Any = "${origin}"` |
|---|---|---|---|
| `origin: "3"` | `'at 3'` | `Point(x=3)` | `'3'` |
| `origin: {class: pkg.Point, x: 3}` | `'at 3'` | `Point(x=3)` | `'3'` |

- **The class the tag names decides**, not the field's type: a tag naming a registered `Leafy` under a `Base` struct field it subclasses, an `Any` or a Callable builds `Leafy`, which the reference reads.
  The decision is construction's own, so the reader spells no variant choice of its own beside construction's.
- **The class itself must be registered.**
  A tag naming an unregistered subclass of a registered leaf builds a struct ([a registration is one construction reaches](../design-decisions/a-registration-is-one-construction-reaches.md#a-registration-is-one-construction-reaches)), which reads as its dict: reading it as the leaf would write it by its parent's serializer, so `other: Point = "${origin}"` would rebuild a `Point` and drop the subclass's own fields.
- **What an expression leaves is the dump form**, as for any typed leaf: a pure `${origin}` leaves `'3'`, which an `Any` holds as text; the tagged spelling no longer escapes that cost.
  Rejected: writing back the tagged dict a leaf was read from, which needs the reader to hand the writer its source spelling, and writes one object two ways.
- **A dict construction refuses reads as written**, the constructor's own exception included, for construction to raise.
- **A dict holding what is yet to be computed reads as written**: a `call:` or `bind:` at any depth below the tag (`_typed_read._computes`).
  An expression below the tag has resolved before the read, so the literal an escape resolves to is a field's text: `{class: pkg.Note, text: $${n}}` reads as the `Note('${n}')` it builds (BUG-310).
  An expression cannot read a call's result before construction ([calls and expressions share one graph](resolution.md#calls-and-expressions-share-one-graph)), and reading through construction would run the call once more per read; FEAT-35 lifts both together.
- **A field below the tag** reads as the member the tagged dict holds: `${origin.x}` is the built `origin.x`.
- **A subscript below the tag is a key of the dict** (`${pair[0]}`), missing as any key the dict lacks, never an index into the leaf it builds: no subscript of a dict answers what the walk missed ([spelling a path](#spelling-a-path)), and indexing the leaf would read the dict whole, before an expression below the tag that the reference's dependencies never named had resolved, so the result hung on key order (BUG-311).
  The spelling that holds no dict, `pair: "1,2"`, is indexed as its leaf ([limitations](../limitations.md#expressions)).

Until BUG-283 the reader walked every dict as a struct's fields before asking its type, so a tagged leaf interpolated as its dict's text and refused a whole-value reference into a `str` field, while the same leaf written as `"3"` read as `Point(x=3)`.

## Delimiting an expression

An expression ends at the first `}` that is neither inside a string literal nor closing a brace the body opened itself, so `${root + "{city}/{city}_{idx}.png"}` is one expression.
That is the rule every host of embedded expressions applies: Python's f-string replacement fields (the hand-written scanner CPython used before 3.12, then the tokenizer of PEP 701), ECMAScript template literals, and OmegaConf, whose 2.1 interpolation grammar replaced a regex.
The old `\$\{([^}]+)\}` regex ended at any `}`, which cut a `str.format`-style template in half.

`_find_expressions` is the one place that answers "where are the expressions in this string?": the predicate, the scan, validation, evaluation, prefixing and the anchor-depth check all iterate its spans, so no two of them can disagree on where an expression stops.

- **A dedicated scanner, not `tokenize`.**
  Delimiting only has to know where a string literal ends: on its opening quote, single or triple, with a backslash escaping the next character whatever the prefix (`r'\''` is one literal).
  Python's tokenizer knows that too, but it tokenizes every other character as well, so where a malformed body ends would hang on how a given Python version's tokenizer fails (pure Python up to 3.11, C since 3.12) instead of the body reaching `ast.parse` and being reported with its text.
  This is the CPython pre-3.12 f-string design.
- **Escapes are delimited the same way**, so `$${a + '}'}` unescapes to `${a + '}'}`.
- **An unclosed body is literal text**, as it was under the regex: a `${` with no closing brace, or one whose string literal never closes (`${'a}`), is not an expression and passes through unchanged. f-strings and template literals reject it instead; confarg keeps treating a stray `${` in a value as text, as it always has.
- An f-string *inside* an expression is scanned as an ordinary literal, which PEP 701's nested same-quote form (`f'{'a'}'`) defeats.
  That is moot: f-strings are outside the whitelist ([safety model](safety-model.md#safety-model)), and the mis-delimited body still fails to parse or to validate.

## Spelling a path

A dot and a constant subscript each spell one path segment: `${svc.web.host}`, `${svc['web']['host']}` and `${svc["web"].host}` read the same key and are the same dependency.
An integer subscript is a list index, `${servers[0].host}` or `${servers[-1].host}`.
The subscript is the only way to write a key that is no identifier: `${svc['web-1'].port}`, `${hosts['example.com']}`.
Precedents agree: in JavaScript `a.b` is `a['b']`, in jq `.foo` is shorthand for `.["foo"]`, and Jinja2 documents `foo.bar` and `foo['bar']` as the same lookup.
An anchor marker takes either spelling too, so `${.['web-1']}`, `${.[0]}` and `${::['web-1']}` read a sibling key, a sibling element and a root key ([reference anchoring](reference-anchoring.md#implementation-constraints)).

**A list index has one spelling** (BUG-133).
A segment is a string, so a string subscript reads an element too: `${xs['1']}` is `${xs[1]}`.
But only the spelling `str()` gives an integer is an index — `0`, `1`, `-1` — and `_list_index` is the one answer to "does this segment spell an index?".
`${xs['+1']}`, `${xs[' 1']}`, `${xs['1_0']}`, `${xs['01']}` and `${xs['-0']}` are `'+1' is not a valid index`, however the key is spelled, constant or computed, though `int()` parses each one.
`_step`, the one walk, asks it on a list, and `_segment_link` asks it to write an index as the integer subscript (`xs[-1]`, not `xs['-1']`).
The CLI's namedtuple positions draw the same line (BUG-97).
Precedents: JSON Pointer (RFC 6901) takes only `0|[1-9][0-9]*` as an array index, and jq refuses any string index into an array.

**A name reads the key it is written as, or is refused** (BUG-132).
Python NFKC-normalizes every identifier it parses (PEP 3131), so `${ﬁle}` (with the `ﬁ` ligature) or `${svc.ﬁle}` would read the key `file`, silently, even when the configuration holds both; a string is never normalized, so `${::['ﬁle']}` and `${svc['ﬁle']}` read the key as written.
`_parse_expression` therefore refuses a body that writes a name Python would read as another, as a body that does not parse: reference extraction skips it, mounting leaves it as written (it would otherwise unparse `ﬁle` as `file`), and validation reports it, naming both spellings and the subscript.
The rule covers every name, a callee (`ｍax(...)`) or a method (`.ｕpper()`) included, since the tokenizer sees them all the same way.
`_reads_as_written` is its one predicate, and the converse already asks it: `_path_to_ast` never spells such a segment with a dot.

Rejected: **read the name as written**, recovering each identifier's token text after parsing.
JavaScript compares identifiers as written and JSONPath (RFC 9535) compares member names by code point, with no normalization, so `${ﬁle}` would read `ﬁle` there.
But the expression language would stop being Python exactly where a reader cannot see it: `ｍax(a, b)` would name no function, and every node carrying a name, a dot's included, would need its token found again by offset.
A refusal changes no answer Python gives, only declines one. jq makes the same call from the other side: its bare identifiers are ASCII, so any other key takes `.["ﬁle"]`.

`_expressions._attribute_chain` is the one answer to "which config path does this node read?".
Reference collection asks it for the dependency graph and evaluation asks it for the value, so a spelling can never be a dependency on one path and read another.
`_expressions._path_to_ast` is the converse, "which expression reads this path?": a dot where the segment is a name, a constant subscript elsewhere, and a first segment that is no name off the root marker (`::['web-1']`).
It spells the prefix of a mounted file and the path a dot run stands for ([reference anchoring](reference-anchoring.md#a-document-is-prefixed-once-by-its-whole-mount-path)).

A computed subscript (`${svc[k]}`) spells no path to the dependency graph: its key is only known once `k` is evaluated, so it is no dependency beyond the names it is computed from.
Evaluation knows the key, and reads it as the segment its constant spelling would be (`_key_segment`): a string is the key, an integer the list index, so with `k: web`, `${svc[k]}` is `${svc['web']}` — the same value, the same `Field 'svc.nope' not found` when it misses, the same `index 5 out of range`.
Evaluation asks `_attribute_chain` with its namespace, and the dependency graph without, so the two differ only in what syntax alone cannot know.
A key that spells no segment (a bool, a float) is Python's subscript alone.

Evaluation reads the path first and falls back on Python's subscript only where the walk stops at a value that is no dict or list (`_eval_path_or`): that is what lets `${name[0]}` index a string, and a value read as an object be indexed.
A dot falls back the same way, as the subscript of the name it spells, so `${svc[k].host}` reads what `${svc[k]['host']}` reads; it never reaches a Python attribute ([safety model](safety-model.md#a-dot-reads-a-key-never-an-attribute)).
A walk that misses inside a dict or a list reports its miss — `Field 'svc.nope' not found`, or `index 5 out of range` — rather than a `KeyError`, and indexes nothing: the walk answers every key their subscript does (next paragraph), and the base read whole would hold expressions the reference's dependencies never named (BUG-311).
The miss is named at the segment that missed, so `${a.nope.x}` reports `a.nope`; when the fallback fails too, the path's own miss is reported the same way.

**An integer key is reached by its digits** (BUG-311).
A dict key no string spells — `{0: x}`, which a caller's data or a YAML `!!int` tag can produce — is reached by a segment spelling that integer (`_list_index`) where the dict holds no key that is the text itself: `${m[0]}`, `${m['0']}`, and `${m[k]}` with `k` either `0` or `'0'`, all read it, as `${xs['1']}` reads a list element.
The path model's segments stay strings, as everywhere else in `dictexpr` and on every channel: a flag, an env var and a file all write a `dict[int, …]` key as its text.
`_step`, the one walk, reaches the key, so the dependency graph names the position the scan names (`m.0` as `("m", 0)`) and the reference waits for exactly the expressions it reads; `key(m[0])`, a node anchor (`${.[0]}`) and the root (`${::[0]}`, which no fallback could index) reach it the same way.
A key equal to the integer is reached as Python's subscript reaches it, so `${m[1]}` reads a key `True` or `1.0`, as the fallback did.

A dict holding both the text and such a key is refused, whichever way the segment is spelled: `Field 'm.0' is ambiguous: '0' could be either the key '0' or the key 0`.
The segment could name either entry, and construction keeps only one of them under a `dict[int, …]`, so no answer would be the built value.
A position the scan names is its key exactly, so an expression held under the key `'0'` of such a dict still resolves: only what an expression spells is refused (`_step`'s `spelled`).

Until BUG-124 a position was a dotted string, so `m.0` named the integer key and the text one alike.
Holding positions as tuples named the integer key `0` while a reference spelled the text `'0'`, which the reference then reached only through the subscript fallback, reading `m` whole before the expressions in it resolved: `${a[0].p}` read a sibling's `${x}` as its text or as `1` by key order alone (BUG-311; BUG-125 made the dot fall back the same way).
Precedent: OmegaConf's interpolation segments are text too, `${m.0}` reaches an integer key `0`, and it refuses a dict holding both `'0'` and `0` when the configuration is created; jq and JSON Pointer have text keys only.

Rejected, for BUG-311:

- **Waiting for the whole base a fallback reads**: a reference whose path misses would wait for every expression below where its walk stopped.
  `${a[0].p}` inside `a` would be a cycle, two such references in one dict a false one (`q` waiting on `s`, `s` on `q`), and a typo inside its own struct (`${.name}`) a `CircularReferenceError` in place of `Field 'svc.name' not found`.
- **Typed segments**, `[0]` the integer key and `['0']` the text one (maintainer-chosen against).
  Every text channel writes a `dict[int, …]` key as text, so `${m[0]}` would miss whatever a file or a flag set and the spelling would depend on the channel; positions would also turn `str | int | ListOp` across the scan, the write-back, the typed reader and the typed merge's walk, which the CLI shares.
- **The text key first**, as before: `${m[0]}` read `'0'` of a dict holding both while construction kept whichever came last, and no path reached the integer key.
- **Only a key of type `int`**: `${m[1]}` would stop reaching `True` and `1.0`, which the fallback reached.

Some nodes spell no path at all: a base not rooted at a name (`${(a if c else b)['x']}`), or a key that is no segment (`${m[flag]}` with `flag: false`).
Their miss has no field to name, so it stays an `ExpressionEvalError`, worded the way a path's detail is: `Error in expression "${(a if c else b)['x']}": key 'x' not found`, or `index 5 out of range` (BUG-134).
Before, the message ended with Python's bare `KeyError` repr, `'x'` or `False`.
The expression is quoted as written, by `_eval_expr`, rather than by unparsing the base, whose tree has had its anchors resolved to absolute paths ([reference anchoring](reference-anchoring.md#implementation-constraints)).
Only a miss is reworded: a value that cannot be indexed keeps Python's own message (`'int' object is not subscriptable`), which already says what went wrong.

The callee of a method call is no path at all: `${name.upper()}` evaluates `name` and calls the method on it, never reading a key `name.upper` ([safety model](safety-model.md#a-method-is-a-string-method)).

Rejected: **runtime subscript first, path second.**
`${m[0]}` would then mean the integer key while the dependency graph, which only sees syntax, recorded the path `m.0` — two answers to one spelling.
Path-first is also the order an attribute already used.

Rejected, for a computed key (BUG-128): **Python's subscript first, the path only to word its miss.**
Before BUG-128 `${svc[k]}` was Python's subscript alone and its miss surfaced as an `ExpressionEvalError` quoting the bare `KeyError` (`'nope'`), so the error a caller caught depended on how the key was spelled.
Keeping that order and naming the path only on a miss would still give one segment two answers: with `k: 0`, `${m[k]}` read the integer key of `{"0": a, 0: b}` while `${m[0]}` read the string one, and `${xs[k]}` with `k: "1"` failed on an element `${xs['1']}` reads — a miss reported as `Field 'xs.1' not found` on a path that exists.
Precedents give a key one meaning however it is written: jq's `.[$k]` is `.["web"]` once `$k` is `"web"`, JavaScript's `a[k]` is `a["web"]`, and Jinja2's `StrictUndefined` raises the same `UndefinedError` for `foo[k]` as for `foo.bar`.

## A position is a sequence of segments

Inside resolution a position — where an expression sits, what a reference reads, how far a dot run climbs — is a tuple of segments (`_Path`), never a dotted string.
The scan names each expression by one, the dependency graph keys its nodes by them, `_anchor_prefix` drops segments from one, and the write-back walks one with `_step`, the walk evaluation reads with.
The file loader holds a node's position within its file the same way, for the clamp on dot runs ([reference anchoring](reference-anchoring.md#dots-are-clamped-at-the-file-root)).
A key holding a dot (`example.com`, which every format can spell as a quoted key) is then one segment like any other: `{"a.b": …}` and `{"a": {"b": …}}` are `("a.b",)` and `("a", "b")`, two nodes that cannot collide.
Joining to a dotted string and splitting it again made them one node, wrote a result back to the wrong key, and climbed one level too many from inside such a key (BUG-124).

A segment is a key or an index, or a pending list op: an expression inside an item a list op still holds sits at `("servers", ListOp.APPEND, "0", "url")`, the op being the key the merged dict holds the item under ([deep merge](../pipeline/deep-merge.md#no-channel-types-an-op)).
`build()` applies most such ops before resolution, so the item is at `("servers", "0", "url")` by then ([below](#a-pending-list-op-is-read-as-its-list)); the op segment remains for an op left pending, and for `resolve_expressions` called on a merged dict directly.
The walk takes it as any dict key, so a node anchor reads through it (`${.host}` beside `url` reads `host` in the same item), and `_spell_path`, the one spelling of a position in a message, writes it as a file does (`servers.__append__.0.url`).
It is never a list index, and a path spells it as a constant subscript, which no source expression can write.

A dict key is a segment as the data holds it, so a segment is typed `Hashable`, in `_Path` as in the default layer's `DataPath` (REF-122).
A YAML `!!int 0:` or a caller's `{0: …}` puts the integer in a position, a caller's dict a date or a tuple, and the walk reaches each as itself.
Typed as text, a segment had the type checker vouch for what the code never guaranteed, and a cast hid each place a key was used as text: only text spells a list index (`_list_index`), which the type now makes every caller ask.
A segment an expression spells (`_attribute_chain`) is text or an op, which a position's type holds.

The dotted form survives only in messages, `Field 'a.b' not found`, which a person reads and nothing parses back.
Precedents keep paths structured for the same reason: jq's `path()`, `getpath` and `setpath` work on arrays of keys (`["a.b"]`), and JSON Pointer (RFC 6901) escapes its separator inside a segment rather than let a key hold it.

## A pending list op is read as its list

An expression reads the list a pending op makes, never the op dict ([design decisions](../design-decisions/a-pending-list-op-is-applied-before-resolution.md#a-pending-list-op-is-applied-before-resolution)).
The default layer applies the ops over what lies below them before resolution wherever the type settles the node is a variable-length sequence (`_default_layer._over_nothing`), so most reach resolution as a list.
Two kinds still hold ops while expressions resolve:

- **A node whose base is an expression**, which settles into its list once that expression has resolved (`resolve_expressions`' `settle` hook, [deep merge](../pipeline/deep-merge.md#a-patch-over-an-expression-patches-its-value)).
  A reference that crosses it by a data key, or reads it whole, depends on every expression below it (`_pending_prefixes` with `crossed`), so it is evaluated after the node settled.
  A path stepping through the op itself, which only an anchor spells from inside an item the op holds, reads that item and depends on nothing more.
- **A node no type settles**, an `Any` or a union with a fixed-length variant, which construction applies or refuses.
  A read crossing or reaching it is refused (`_read_through`, `MissingReferenceError.pending_list_ops`): the op dict is never handed out as the value, so `${len(a)}` is an error rather than the count of its keys.

## Referencing a whole subtree

A reference is a path, not a leaf selector: `_get_nested` returns whatever sits at that path, so `${db}` is as valid as `${db.port}` and substitutes the entire node — dict, list or scalar.
Every expression inside the node resolves first, so what is substituted holds no `${...}`; a node that holds the referencing expression itself is therefore a cycle ([resolution](resolution.md#a-reference-reads-everything-its-path-reaches)).

**Value semantics, not identity.**
Resolution finishes before construction begins ([pipeline](../pipeline/stages.md#the-pipeline)), so what a site references is raw data, never an object.
Construction then walks the resolved dict with no memo keyed by node identity, and two sites referencing one node yield two objects that are equal and not identical. confarg builds a value, not an object graph: sharing one instance between two fields is a dependency-injection concern and stays out of scope, which is the same boundary that keeps the library free of a container ([design decisions](../design-decisions/no-custom-types-required.md#no-custom-types-required)).

**The substituted node is the live sub-dict, not a copy**, unless it holds a leaf read as its object ([above](#a-typed-leaf-reads-as-its-object)), which is substituted as a copy.
`_get_nested` hands back the node itself, so after `resolve()` the referencing path and the referenced path are one dict.
`build()` hides that — it constructs from the dict and drops it — but the three-step seam ([pipeline](../pipeline/api-seams.md#public-api-seams)) exposes it: mutating `resolved["db"]` in place also mutates every path that referenced it, and, when no expression is written in `db`, the caller's own `data["db"]`, which resolution does not copy ([resolution](resolution.md#resolution-copies-only-what-it-writes)).
Copying on substitution would pay a deep copy per reference to protect a caller the seam does not invite (its documented use is to inspect and dump), so the aliasing stands as a limitation ([limitations](../limitations.md#expressions)) rather than a defect.

**The class key travels with the node.**
A referenced struct carries its `class` key along, and `_construct_struct_dispatch` honors a tag even on a non-union field ([types](../types/construction.md#union-construction)).
The referencing field's *declared* type therefore governs what is built: annotated with the tagged class it constructs, annotated with a leaf type it is a coercion error — `${db.port}` is the reference for a single field.
