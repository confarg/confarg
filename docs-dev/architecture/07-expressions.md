# Expressions and variable interpolation

## Engine independence

`dictexpr` resolves `${...}` in string values of a plain nested dict. It knows nothing
about channels, files or dataclasses (imports: stdlib and `confarg.exceptions`), so it can be
used and tested on its own. Paths are resolved against the **whole** merged dict, which is
why features such as locals need no engine support ([08](08-locals.md)).

## Resolution algorithm

`resolve_expressions` (called by `build()` and `resolve()`):

1. scan for expression strings (returns the input unchanged if there are none);
2. deep-copy, then extract each expression's references;
3. topologically sort (Kahn); a cycle raises `CircularReferenceError`;
4. validate every expression's AST;
5. evaluate in dependency order, writing results back so later expressions see them.

Only references that are themselves expressions become graph edges; references to plain
values are already resolved.

Steps 2, 4 and 5 each need a parsed AST, but a unique expression text is parsed once: every
parse site goes through the module-level `_parse_expression` cache (keyed by the raw `${...}`
body after anchor stripping). The Kahn sort is linear in the graph size (`V + E`): a reverse
adjacency list records who depends on each node, so releasing a node touches only its direct
dependents. Both matter only for large configurations — a config with thousands of chained
expressions is the only case that felt the old quadratic sort and triple parse.

Resolution happens **after** all sources are merged. That is the point of the design:
overriding `resources.memory_gb` on the CLI recomputes a `${resources.memory_gb * 0.8}`
written in a file.

## Value typing

A string that is exactly one `${expr}` keeps the expression's Python type (int, list, …).
Anything with surrounding text, including surrounding whitespace, is string interpolation.
`$${...}` is an escape producing the literal `${...}`.

## Referencing a whole subtree

A reference is a path, not a leaf selector: `_get_nested` returns whatever sits at that path,
so `${db}` is as valid as `${db.port}` and substitutes the entire node — dict, list or scalar.

**Value semantics, not identity.** Resolution finishes before construction begins
([01](01-pipeline-and-contracts.md#the-pipeline)), so what a site references is raw data, never
an object. Construction then walks the resolved dict with no memo keyed by node identity, and
two sites referencing one node yield two objects that are equal and not identical. confarg
builds a value, not an object graph: sharing one instance between two fields is a
dependency-injection concern and stays out of scope, which is the same boundary that keeps the
library free of a container ([10](10-design-decisions.md#no-custom-types-required)).

**The substituted node is the live sub-dict, not a copy.** `_get_nested` hands back the node
itself, so after `resolve()` the referencing path and the referenced path are one dict.
`build()` hides that — it constructs from the dict and drops it — but the three-step seam
([01](01-pipeline-and-contracts.md#public-api-seams)) exposes it: mutating `resolved["db"]` in
place also mutates every path that referenced it. Copying on substitution would pay a deep copy
per reference to protect a caller the seam does not invite (its documented use is to inspect and
dump), so the aliasing stands as a limitation ([11](11-limitations.md#expressions)) rather than a
defect.

**The union tag travels with the node.** A referenced struct carries its `class` key along, and
`_construct_struct_dispatch` honors a tag even on a non-union field
([05](05-types-and-construction.md#union-construction)). The referencing field's *declared* type
therefore governs what is built: annotated with the tagged class it constructs, annotated with a
leaf type it is a coercion error — `${db.port}` is the reference for a single field.

## Safety model

Expressions come from config files, env and argv, so they are evaluated by a small
interpreter over a whitelisted AST, never `eval`:

- allowed nodes: constants, names, attributes, integer subscripts, arithmetic, comparisons,
  boolean ops, conditional expressions, calls (`_ALLOWED_NODES`);
- calls only to whitelisted free functions (`abs min max round ceil floor str int float bool
  len`) and string methods (`upper lower strip split replace startswith endswith join`); no
  indirect calls;
- no attribute starting with `__`;
- consequently no literals for lists/dicts/sets, no slices, no comprehensions, no lambdas, no
  f-strings; the `${...}` regex also forbids `}` inside an expression.

`a.b` is first tried as a config path; only if that fails is it a real attribute access
(e.g. the receiver of a string method), and a miss is reported as a missing field rather
than an `AttributeError` on `dict`.

## Deferral rule

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
cross-channel divergence [09](09-invariants.md#cross-channel-parity) forbids. `build()`
validates the resolved result, so an expression landing outside a `Literal` still fails,
identically everywhere.

## Reference anchoring

Because a file can be mounted at any depth ([02](02-files-and-env.md#mounting)), a path means
nothing until it is anchored. There are three anchors, and they answer three different
questions:

| Spelling | Anchor | Resolved |
|---|---|---|
| `${foo.bar}` | the **file** that wrote it, whatever the depth within that file | at mount time |
| `${::foo.bar}` | the **configuration** root | at mount time |
| `${.foo}`, `${..foo}` | the **node** that wrote it, one level up per dot | at evaluation time |

A single unnested file is the degenerate case where the first two coincide, so its text is
never rewritten and survives `merge()` → `dump_file()` verbatim.

### Why the node anchor resolves late

The file anchor is a *rewrite*, applied while files are mounted, because `build()` takes a plain
dict with no side channel:

| Stage | Action |
|---|---|
| `_files._resolve_dict` / `_resolve_list` | thread the path within the file; `prefix_references` each included document by it *before* merging siblings (siblings belong to the including file); `check_anchor_depth` each expression against that same path |
| `_files._load_subpath_files`, `_pipeline._load_cli_config` | prefix by the mount subpath (env pointers and `--config.<path>`) |
| end of `_merge_sources` | `canonicalize_references` turns remaining `${::x}` into `${x}` |

The prefix is uniform per file, **not per position**, which is what lets one fragment be
mounted at several depths and mean the same thing — and is exactly why the node anchor cannot
join it. A position-relative path has no fixed answer until the node has a position, which for
an element appended by `--config.<path>+` is not true until the merge is over.

So the dot markers are carried through the merge untouched and interpreted once, in
`resolve_expressions`. That is also what makes them the only spelling available to an appended
fragment, whose bare names are still anchored at the merged root by default.

### A relative reference is never serialized as an absolute path

`canonicalize_references` resolves `${::x}`, so the merged dict no longer depends on a marker
whose meaning is already fixed. It deliberately leaves `${.x}` alone.

Rewriting it would mean writing `${servers.3.host}` into the dumped configuration, pinning the
element to the index it happened to hold. Reordering the list, inserting ahead of it, or lifting
it into a file of its own would then break it — silently, because nothing in the file would look
wrong. Not naming its index is the property the node anchor exists to provide, and `merge()` is
the moment it would be lost. The cost, accepted: the merged dict is *not* uniformly root-anchored
any more, so "canonical form" now means the file and configuration anchors are resolved and the
node anchor is preserved.

### Implementation constraints

- Marker detection (`_anchor_markers`) is **lexical, not a regex**: a tokenizer distinguishes the
  dot of `1.5` (one NUMBER) or `','.join(x)` (a STRING first) from a marker, while a keyword
  before a dot (`a if .b else c`) still starts an operand. `_unname_anchor` is lexical for the
  same reason (never touch string literals). Two details it must keep honouring: Python tokenizes
  `...` as a single ellipsis token while `..` arrives as two dots, and a `::` is a root marker
  only when the innermost enclosing bracket is not `[` — inside a subscript it is a slice step,
  which is what keeps `items[::2]` available to [FEAT-12](../todo/features/FEAT-12-scoped-expression-expansion.md).
  Parentheses reopen the marker: `items[(::step)]`.
- **The node anchor is resolved on the tree, never on source** (`_AnchorResolver`). An absolute
  path may hold a list index or a key that is no identifier — `dbs.0.host`, `svc.web-1.host` —
  which is a fine `ast.Attribute` chain for `_attribute_chain` to read back but not Python anyone
  could parse. Rewriting the text instead would miscompile `web-1.host` into a subtraction.
- `_Prefixer` rewrites only `ast.Name` bases. That is correct only because lambdas and
  comprehensions are not in `_ALLOWED_NODES`, so every non-function `Name` is a reference
  base. **Adding a binding construct to the whitelist breaks prefixing.**
- `_Prefixer` and `_AnchorResolver` both exempt the stand-in names (`__ROOT__`, `__UP<n>__`),
  which is the same static exemption [FEAT-21](../todo/features/FEAT-21-app-supplied-expression-functions.md)
  and [FEAT-22](../todo/features/FEAT-22-environment-namespace-in-expressions.md) need for `fn`
  and `env`.

### Dots are clamped at the file root

`check_anchor_depth` refuses a dot run that climbs past the root of the file that wrote it,
while the file is being loaded and its own `path_in_file` is still known. Without it a fragment
using `..` would mean different things at different mount depths, which is the property the file
anchor exists to prevent; `::` is the marked way out. The check needs no mount prefix, which is
why it holds for an appended fragment too.

Known limit: `--config.<path>+` appends at an index that depends on the current list
length, unknowable while loading, so an appended fragment's **bare** references are left anchored
at the merged root instead of being prefixed by a guess. Its dot references are unaffected.
