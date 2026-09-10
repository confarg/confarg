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

Resolution happens **after** all sources are merged. That is the point of the design:
overriding `resources.memory_gb` on the CLI recomputes a `${resources.memory_gb * 0.8}`
written in a file.

## Value typing

A string that is exactly one `${expr}` keeps the expression's Python type (int, list, …).
Anything with surrounding text, including surrounding whitespace, is string interpolation.
`$${...}` is an escape producing the literal `${...}`.

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
nothing until it is anchored:

- a bare `${foo.bar}` refers to `foo.bar` **in the file that wrote it**, whatever its depth in
  that file;
- `${.foo.bar}` (leading dot) refers to `foo.bar` in the **merged document**.

A single unnested file is the degenerate case where both coincide, so its text is never
rewritten and survives `merge()` → `dump_file()` verbatim.

`build()` takes a plain dict with no side channel, so the anchor is resolved while files
are mounted:

| Stage | Action |
|---|---|
| `_files._resolve_dict` / `_resolve_list` | thread the path within the file; `prefix_references` each included document by it *before* merging siblings (siblings belong to the including file) |
| `_files._load_subpath_files`, `_pipeline._load_cli_config` | prefix by the mount subpath (env pointers and `--config.<path>`) |
| end of `_merge_sources` | `canonicalize_references` turns remaining `${.x}` into `${x}` |

The prefix is uniform per file, not per position, which is what lets one fragment be
mounted at several depths and mean the same thing. After canonicalization the merged dict
is uniformly anchored at its own root, so a dumped merged config is itself a well-formed
fragment that can be included elsewhere. `.foo` references are left alone by
`prefix_references` because their document is not known until every file is mounted.
`resolve()`/`build()` still accept the marker (strip it) for hand-built dicts.

Implementation constraints:

- Marker detection (`_anchor_dots`) is **lexical, not a regex**: a tokenizer distinguishes the
  dot of `1.5` (one NUMBER) or `','.join(x)` (a STRING first) from a marker, while a keyword
  before a dot (`a if .b else c`) still starts an operand. `_unname_anchor` is lexical for the
  same reason (never touch string literals).
- `_Prefixer` rewrites only `ast.Name` bases. That is correct only because lambdas and
  comprehensions are not in `_ALLOWED_NODES`, so every non-function `Name` is a reference
  base. **Adding a binding construct to the whitelist breaks prefixing.**

Known limit: `--config.<path>+` appends at an index that depends on the current list
length, unknowable while loading, so an appended fragment's references are left anchored
at the merged root instead of being prefixed by a guess.
