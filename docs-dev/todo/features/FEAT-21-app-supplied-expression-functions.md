# FEAT-21 — Expression functions supplied by the application

**Where:** `src/confarg/dictexpr/_expressions.py` (`_SAFE_FUNCTIONS`, `_collect_names`,
`_Prefixer`), `src/confarg/_api.py`, `src/confarg/_pipeline.py` · **Filed:** 2026-09-22 ·
*(inferred — design discussed with the maintainer, no code written)*
**Effort:** L · **Risk:** high · **Impact:** behavior

An expression can only recombine values that are already in the document, using a fixed table of
builtins (`abs min max round ceil floor str int float bool len` and a few string methods,
[07](../../architecture/07-expressions.md#safety-model)). A derivation whose *computation*
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
  ([07](../../architecture/07-expressions.md#referencing-a-whole-subtree));
- the Kahn sort already orders evaluation by dependency, so every `${...}` *inside* `db` is
  resolved before the function runs: the dependency graph is the execution plan
  ([07](../../architecture/07-expressions.md#resolution-algorithm));
- `merge()` stays pure — the call text survives into `dump_file(merge(...))`, and only
  `resolve()` / `build()` / `load()` become effectful.

The function receives plain resolved data, not a constructed object, because resolution finishes
before construction begins. An application that wants its own type back calls
`confarg.from_dict(DbConfig, node)` inside the function; the seam composes.

## The crux: prefixing has to know the names

`_Prefixer.visit_Name` leaves a name alone only if it is in `_SAFE_FUNCTIONS`
(`_expressions.py:782`), and `_collect_names` skips those same names instead of treating them as
reference bases. Both run at **mount time, inside `merge()`** — so a table visible only to
`resolve()` would rewrite `${label_count(db)}` in a mounted fragment into
`${sub.label_count(sub.db)}` and then fail to find it. That decides the spelling more than taste
does:

| Spelling | How the table reaches the prefixer | Cost |
|---|---|---|
| `${label_count(db)}`, global registry | import-time global state | `resolve()` stops being a pure function of its dict; a merged dict resolves in one application and not in another |
| `${label_count(db)}`, a `functions=` parameter | threaded through `merge`, `resolve`, `build`, `load` **and** the five front-ends | a large API surface for one feature; `resolve(data)`'s deliberately type-blind signature grows |
| **`${fn.label_count(db)}`, a reserved namespace** | it does not have to — a static, lexical exemption beside `_ROOT_ANCHOR` in `visit_Name` | one more reserved name ([FEAT-3](FEAT-3-reserved-sentinel-key-registry.md)), derived by *real field wins* |

The third is the one to start from. It is the only spelling where mounting stays correct without
the table being visible during `merge()`, so how the table is supplied becomes an independent
question instead of the question. It reads as what it is in a config file. And it avoids a
collision the bare form carries: because `_collect_names` stops treating a whitelisted name as a
reference base, **a registered name shadows a same-named config key everywhere**. With `len` that
is a small documented set; with application names it is unbounded and different per application.

`locals` is the precedent for a reserved namespace derived from the target rather than
configured ([08](../../architecture/08-locals.md#derived-name)): `_fn` when the target really has
an `fn` field, decided by the same `_segment_names_real_field` predicate
([03](../../architecture/03-cli-parsing.md#real-field-wins)).

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
- **Keyword arguments** already come for free: `_collect_names_from_call` walks `node.keywords`.

## Rejected

Letting a config file name any importable path (`${myapp.labels.count(db)}`). That hands
arbitrary code execution to whoever writes a file, before a single type has been checked. The
contrast worth stating: a `Callable` field already lets configuration name an importable target
([06](../../architecture/06-callables.md)), but it is called at *construction*, against a
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
([07](../../architecture/07-expressions.md#referencing-a-whole-subtree)). Bicep and CUE stay with
a curated standard library and no extension point at all.
