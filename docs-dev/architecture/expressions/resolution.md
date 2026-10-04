# The expression engine

## Engine independence

`dictexpr` resolves `${...}` in string values of a plain nested dict. It knows nothing
about channels, files or dataclasses (imports: stdlib and `confarg.exceptions`), so it can be
used and tested on its own. Paths are resolved against the **whole** merged dict, which is
why features such as locals need no engine support ([locals](../locals.md)).

## Resolution algorithm

`resolve_expressions` (called by `build()` and `resolve()`):

1. scan for expression strings (returns the input unchanged if there are none);
2. deep-copy, then extract each expression's references;
3. topologically sort (Kahn); a cycle raises `CircularReferenceError`;
4. validate every expression's AST;
5. evaluate in dependency order, writing results back so later expressions see them.

Only expressions are graph nodes; a reference that reaches nothing but plain values reads
values already resolved, and is no edge. Which expressions a reference does reach is the next
section.

Steps 2, 4 and 5 each need a parsed AST, but a unique expression text is parsed once: every
parse site goes through the module-level `_parse_expression` cache (keyed by the raw `${...}`
body after anchor stripping). The Kahn sort is linear in the graph size (`V + E`): a reverse
adjacency list records who depends on each node, so releasing a node touches only its direct
dependents. Both matter only for large configurations — a config with thousands of chained
expressions is the only case that felt the old quadratic sort and triple parse.

Resolution happens **after** all sources are merged. That is the point of the design:
overriding `resources.memory_gb` on the CLI recomputes a `${resources.memory_gb * 0.8}`
written in a file.

## A reference reads everything its path reaches

`_dependency_graph` answers "which expressions must resolve before this one?". A reference
depends on every expression its path reaches, not only on one sitting at exactly that path:

| Reached | Example | Why it is read |
|---|---|---|
| at the path | `${db.port}`, `db.port` is `${base + 1}` | the value itself |
| below it | `s=${svc}`, `svc.h` is `${base}` | the whole subtree is stringified, passed to a function or substituted |
| above it | `${a.b.c}`, `a.b` is `${d}` | the path reads into what `a.b` resolves to |

The first was the only edge before BUG-123, so the other two read the raw `${...}` text when the
referencing expression happened to sort first. A pure `${svc}` only hid it because it substitutes
the live sub-dict ([values and references](values-and-references.md#referencing-a-whole-subtree)),
which the later resolution of `svc.h` filled in after the fact.

**A path is named as the scan names it.** The scan names a list element by its position
(`xs.1`), while a reference spells what it likes: `${xs[-1]}`, `${xs['1']}`. `_scan_path` walks
the reference down the data with `_step`, the same step `_get_nested` reads a value with, so the
graph depends on exactly the node evaluation will reach: `xs[-1]` of a two-item list is `xs.1`.
The data's shape is fixed by then, because resolution only ever replaces a string leaf. The walk
stops where the data stops answering — a missing key, or the inside of an expression not yet
resolved — and keeps the rest as written, which the "above it" rule covers: `${xs[-1]}` with
`xs: ${ys}` depends on `xs`, whose length is not known yet.

**A reference to an ancestor from inside it is a cycle.** `svc.a: ${svc}` reads `svc`, which holds
`svc.a` itself, so `svc.a` depends on itself and `CircularReferenceError` names it. Before, it
substituted a dict that contained itself. This holds whatever reads the ancestor, `${len(svc)}` and
`${svc[k]}` included: the graph is built from syntax, and cannot tell that `len` only counts keys
or which key `k` will name ([limitations](../limitations.md#expressions)). The configuration root
is the ancestor of every expression, so an anchor that names it whole — `${::}`, `${::[k]}` —
is a cycle too; its path is the empty one, and the index below answers it with every expression
([reference anchoring](reference-anchoring.md#implementation-constraints)). CUE draws the same line
— a struct that references itself from inside is a structural cycle — while engines that resolve
lazily on access (OmegaConf, Jsonnet, Nix) need no ordering at all, and so detect such a cycle,
if at all, only once something walks the value.

Graph nodes stay expression paths. An index from each path holding an expression to the
expressions at or below it answers the "below" rule with one lookup per reference, and the "above"
rule checks the reference's own prefixes, so a cycle message names expressions only, never an
intermediate dict.

Rejected:

- **Lazy, resolve-on-access evaluation**, as OmegaConf does. It needs no graph, but the engine
  evaluates in order and writes each result back, and a static graph is what reports a cycle,
  naming its members, before anything is evaluated.
- **Subtree nodes in the graph** (`svc` depending on everything below it). Fewer edges when many
  references read one large subtree — the index adds one edge per expression in it, per
  reference — but a cycle message would then list dicts that are no expression.
