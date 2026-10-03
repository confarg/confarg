# Reference anchoring

Because a file can be mounted at any depth ([config files](../config-files/mounting.md#mounting)), a path means
nothing until it is anchored. There are three anchors, and they answer three different
questions:

| Spelling | Anchor | Resolved |
|---|---|---|
| `${foo.bar}` | the **file** that wrote it, whatever the depth within that file | at mount time |
| `${::foo.bar}` | the **configuration** root | at mount time |
| `${.foo}`, `${..foo}` | the **node** that wrote it, one level up per dot | at evaluation time |

A single unnested file is the degenerate case where the first two coincide, so its text is
never rewritten and survives `merge()` → `dump_file()` verbatim.

## Why the node anchor resolves late

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

## A relative reference is never serialized as an absolute path

`canonicalize_references` resolves `${::x}`, so the merged dict no longer depends on a marker
whose meaning is already fixed. It deliberately leaves `${.x}` alone.

Rewriting it would mean writing `${servers.3.host}` into the dumped configuration, pinning the
element to the index it happened to hold. Reordering the list, inserting ahead of it, or lifting
it into a file of its own would then break it — silently, because nothing in the file would look
wrong. Not naming its index is the property the node anchor exists to provide, and `merge()` is
the moment it would be lost. The cost, accepted: the merged dict is *not* uniformly root-anchored
any more, so "canonical form" now means the file and configuration anchors are resolved and the
node anchor is preserved.

A `::` is dropped only before a name: `${::name}` becomes `${name}`, but `${::['web-1']}` stays as
written (BUG-126). No plain path reads a root key that is no identifier — `${['web-1']}` is a list
literal — so the marker is the only spelling it has, and `resolve_expressions` reads it as it
reads any other.

## Implementation constraints

- Marker detection (`_anchor_markers`) is **lexical, not a regex**: a tokenizer distinguishes the
  dot of `1.5` (one NUMBER) or `','.join(x)` (a STRING first) from a marker, while a keyword
  before a dot (`a if .b else c`) still starts an operand. `_unname_anchor` is lexical for the
  same reason (never touch string literals). Two details it must keep honouring: Python tokenizes
  `...` as a single ellipsis token while `..` arrives as two dots, and a `::` is a root marker
  only when the innermost enclosing bracket is not `[` — inside a subscript it is a slice step,
  which is what keeps `items[::2]` available to [FEAT-12](../../todo/features/FEAT-12-scoped-expression-expansion.md).
  Parentheses reopen the marker: `items[(::step)]`.
- **The node anchor is resolved on the tree, never on source** (`_AnchorResolver`). An absolute
  path may hold a list index, a key that is no identifier or a key holding a dot — `dbs.0.host`,
  `svc.web-1.host`, `hosts['example.com'].port` — each one segment of the node's position
  ([values and references](values-and-references.md#a-position-is-a-sequence-of-segments)),
  which is a fine `ast.Attribute` chain for `_attribute_chain` to read back but not Python anyone
  could parse. Rewriting the text instead would miscompile `web-1.host` into a subtraction.
- **The stand-in owns a dot only before a name.** A marker is followed by a name (`.host`), a
  subscript (`.['web-1']`, `.[0]`) or nothing (`.`), and the subscript is the only spelling of a
  sibling key that is no identifier or of a sibling list element
  ([values and references](values-and-references.md#spelling-a-path)). So `_name_anchor` writes
  `__UP1__.host` but `__UP1__['web-1']` and `__UP1__`, each a path `_attribute_chain` reads as it
  reads `x.host`, `x['web-1']` and `x`. `_anchor_markers` is the one answer to "does a name
  follow this marker?", and the same answer decides whether `canonicalize_references` may drop a
  `::` ([below](#a-relative-reference-is-never-serialized-as-an-absolute-path)). jq spells it
  the same way — `.foo` is shorthand for `.["foo"]`, and `.[0]` indexes the input — as does
  JSONPath with `$['web-1']`. Before BUG-126 the stand-in always took the dot, and
  `__UP1__.[0]` did not parse.
- **`_AnchorResolver` rewrites only the stand-in** (`__UP1__` → `svc`), never the chain after it.
  Each segment the expression spells keeps its own node, so a subscript stays a subscript: when
  the path read misses, its fallback indexes by the key it spells, the integer `0` of
  `${.m[0]}` or `${.[0]}` on a YAML `{0: x}`, where a rebuilt attribute could only index by the
  string `"0"` ([values and references](values-and-references.md#spelling-a-path)). Before
  BUG-125 this was a safety rule too: the attribute fallback was `getattr`, so
  `${.a['__class__'].mro}` rebuilt as `a.__class__.mro` would have bypassed the dunder ban,
  which validation applies to attributes as written.
- **The configuration root has no node to stand for.** A path is a `Name` and the links after it,
  and the empty path has no `Name`. So where the stand-in names the root — `::`, or a dot run that
  climbs all the way up — the first segment after it becomes the base name instead (`_segment`,
  the one reading of a single link that `_attribute_chain` also asks): `${::['web-1']}` reads the
  key `web-1`. The base name is a string, so a non-string key at the root is not reachable
  ([limitations](../limitations.md#expressions)). A stand-in still in the tree after that names
  the root whole (`${::}`, `${..}` from one level down, `${::[k]}`); `_collect_names` reads it as
  the empty path, and since the root holds every expression, it is the cycle any reference to an
  ancestor is ([resolution](resolution.md#a-reference-reads-everything-its-path-reaches)).
- `_Prefixer` rewrites only `ast.Name` bases. That is correct only because lambdas and
  comprehensions are not in `_ALLOWED_NODES`, so every non-function `Name` is a reference
  base. **Adding a binding construct to the whitelist breaks prefixing.**
- `_Prefixer` and `_AnchorResolver` both exempt the stand-in names (`__ROOT__`, `__UP<n>__`),
  which is the same static exemption [FEAT-21](../../todo/features/FEAT-21-app-supplied-expression-functions.md)
  and [FEAT-22](../../todo/features/FEAT-22-environment-namespace-in-expressions.md) need for `fn`
  and `env`.

## Dots are clamped at the file root

`check_anchor_depth` refuses a dot run that climbs past the root of the file that wrote it,
while the file is being loaded and its own `path_in_file` is still known. It asks
`_anchor_prefix`, the question resolution asks of the same run, with the position held as
segments, so a key holding a dot is one level to both. Without it a fragment
using `..` would mean different things at different mount depths, which is the property the file
anchor exists to prevent; `::` is the marked way out. The check needs no mount prefix, which is
why it holds for an appended fragment too.

Known limit: `--config.<path>+` appends at an index that depends on the current list
length, unknowable while loading, so an appended fragment's **bare** references are left anchored
at the merged root instead of being prefixed by a guess. Its dot references are unaffected.
