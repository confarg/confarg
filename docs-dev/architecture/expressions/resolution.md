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
