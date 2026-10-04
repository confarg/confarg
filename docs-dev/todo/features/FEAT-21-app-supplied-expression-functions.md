# FEAT-21 — Expression functions supplied by the application

**Where:** `src/confarg/dictexpr/_expressions.py` (`_SAFE_FUNCTIONS`, `_collect_names`,
`_Prefixer`), `src/confarg/_api.py`, `src/confarg/_pipeline.py` · **Filed:** 2026-09-22 ·
*(inferred — design discussed with the maintainer, no code written)*
**Effort:** L · **Risk:** high · **Impact:** behavior

An expression can only recombine values that are already in the document, using a fixed table of
builtins (`abs min max round ceil floor str int float bool len` and a few string methods,
[07](../../architecture/expressions/safety-model.md#safety-model)). A derivation whose *computation*
belongs to the application has no spelling at all: the number of labels behind a database query,
the length of a file in a format confarg does not read, a git revision, a hostname looked up per
environment.

The application can stage such a value by hand across the three-step seam — resolve what the
computation needs, run it, inject the result into the merged dict, build. That works today and is
often the right answer. What it cannot do is put the derivation *in the configuration*: the
result is a bare number that `dump_file(merge(...))` cannot write back as a derivation, no source
can override the inputs and see it recomputed, and every front-end entry point has to repeat the
staging by hand.

## The shape

No new syntax is required. `ast.Call` is already in `_ALLOWED_NODES`; only the *name table* is
fixed. Three behaviors that already exist do the work:

- a reference is a path, not a leaf selector, so one argument can hand the function a **whole
  node** — `${label_count(db)}` passes the credentials as a dict
  ([07](../../architecture/expressions/values-and-references.md#referencing-a-whole-subtree));
- the Kahn sort already orders evaluation by dependency, so every `${...}` *inside* `db` is
  resolved before the function runs: the dependency graph is the execution plan
  ([07](../../architecture/expressions/resolution.md#resolution-algorithm));
- `merge()` stays pure — the call text survives into `dump_file(merge(...))`, and only
  `resolve()` / `build()` / `load()` become effectful.

The function receives plain resolved data, not a constructed object, because resolution finishes
before construction begins. An application that wants its own type back calls
`confarg.from_dict(DbConfig, node)` inside the function; the seam composes.

## The crux: prefixing has to know the names — gone since BUG-120

This section used to argue that `_Prefixer` and `_collect_names`, which run at **mount time,
inside `merge()`**, exempted a name by looking it up in `_SAFE_FUNCTIONS`, so a table visible only
to `resolve()` would turn a mounted fragment's `${label_count(db)}` into
`${sub.label_count(sub.db)}`; and that a registered name would shadow a same-named key everywhere.
Neither holds any more: a name is a function exactly when it is a call's callee, a syntactic rule
that needs no table (`_function_name`,
[07](../../architecture/expressions/safety-model.md#a-function-is-named-only-by-a-call)). The
fragment becomes `${label_count(sub.db)}` whatever the table holds, and `${label_count}` reads
the key. The table only has to reach validation and evaluation, in `resolve()`:

| Spelling | What mount time needs | Cost |
|---|---|---|
| `${label_count(db)}`, global registry | nothing | `resolve()` stops being a pure function of its dict; a merged dict resolves in one application and not in another |
| `${label_count(db)}`, a `functions=` parameter | nothing | threaded through `resolve`, `build`, `load` **and** the five front-ends, not `merge`; `resolve(data)`'s deliberately type-blind signature grows |
| `${fn.label_count(db)}`, a reserved namespace | a lexical exemption for `fn` beside `_ROOT_ANCHOR` in `visit_Name`, and the matching skip in `_collect_names` | one more reserved name ([FEAT-3](FEAT-3-reserved-sentinel-key-registry.md)), derived by *real field wins* |

The namespace was the one to start from while it was the only spelling that mounted correctly and
did not shadow keys. BUG-120 took both advantages away. What it still has is that it reads as what
it is in a config file, and that application names cannot collide with a builtin the whitelist
gains later. Weigh that again before building.

`locals` is the precedent for a reserved namespace derived from the target rather than
configured ([08](../../architecture/locals.md#derived-name)): `_fn` when the target really has
an `fn` field, decided by the same `_segment_names_real_field` predicate
([03](../../architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins)).

## Open, to record rather than settle now

- **Caching.** Two sites carrying the same call text are two graph nodes, so the function runs
  twice; a query would be issued twice. OmegaConf added `use_cache` on resolvers for exactly
  this. Cache by (name, resolved arguments) within one `resolve()` call, or not at all.
- **Errors.** An exception raised inside an application function must be wrapped with the
  expression text and the config path, the way the engine's own failures are, rather than
  letting an `OperationalError` escape `confarg.load`.
- **What may trigger it.** `--help` does not resolve today and must not start; a future
  `confarg check` ([FEAT-9](FEAT-9-confarg-check-command.md)) has to decide whether validating a
  configuration is allowed to run application code.
- **Keyword arguments** are half there: `_collect_names_from_call` walks `node.keywords`, but
  `ast.keyword` is not in `_ALLOWED_NODES`, so validation refuses `${round(x, ndigits=2)}` today.

## Rejected

Letting a config file name any importable path (`${myapp.labels.count(db)}`). That hands
arbitrary code execution to whoever writes a file, before a single type has been checked. The
contrast worth stating: a `Callable` field already lets configuration name an importable target
([06](../../architecture/callables.md)), but it is called at *construction*, against a
declared signature, with kwargs coerced through `construct`. An application-owned table is
strictly more restrictive than what confarg already permits, which is why this does not breach
the safety model — the application owns the table, the configuration may only name what is in it.

## When not to use it

For a value behind a database query the staged seam is still better: the application opens the
connection anyway to load the data, and a resolver opens a second one at resolve time, inside a
function that must not fail in `--help` and cannot be given the pool. The feature earns its keep
on cheap, idempotent derivations — counting entries of a file confarg cannot parse, a revision
string, a lookup with no connection to manage.

Adjacent to [FEAT-12](FEAT-12-scoped-expression-expansion.md): same whitelist, other axis — that
one adds fixed nodes and builtins, this one makes the call table extensible. Composes with
[FEAT-19](FEAT-19-app-declared-defaults.md), where a declared default may carry the call.

Precedents: OmegaConf and Hydra's `register_new_resolver` is the global-registry row above, with
`${name:arg}` syntax confarg does not need since calls already parse; jsonargparse answers the
same question from the other end with `apply_on="instantiate"` links, which require the framework
to own instantiation order — a dependency-injection container, out of scope
([07](../../architecture/expressions/values-and-references.md#referencing-a-whole-subtree)). Bicep and CUE stay with
a curated standard library and no extension point at all.
