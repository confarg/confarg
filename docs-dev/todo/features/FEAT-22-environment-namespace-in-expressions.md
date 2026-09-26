# FEAT-22 — The process environment as an expression namespace

**Where:** `src/confarg/dictexpr/_expressions.py` (`_collect_names`, `_Prefixer`, the resolver's
namespace), `src/confarg/_files.py` (include resolution), `src/confarg/_pipeline.py`,
`src/confarg/_tags.py` · **Filed:** 2026-09-22 · *(inferred — design discussed with the
maintainer, no code written)*
**Effort:** L · **Risk:** high · **Impact:** behavior

Two things that look separate and are not:

1. `${env.APP_ENV}` in any expression — the process environment readable by name, rather than
   only as a *source* of field values gated by `env_prefix`;
2. `__include__: configs/${env.APP_ENV}.yaml` — an include path that selects a file per
   deployment.

(2) is the request; (1) is what makes it sound, and it is worth having on its own.

## Why an include path cannot carry an ordinary expression

Includes are resolved in `_files._resolve_dict` while a file is being *loaded*, which is step 2 of
`_pipeline._merge_sources`; expressions are resolved after step 3, against the merged document
([01](../../architecture/01-pipeline-and-contracts.md#the-pipeline)). A document cannot choose its
own inputs: the content depends on the include, and the include would depend on the content.

So an include path can only reference something known *before any file is read*. Several
namespaces qualify mechanically — `_merge_sources` has `cli_data` in its signature and parses the
environment into `env_data` at step 1, both before `_load_subpath_files` at step 2 — but only one
qualifies *semantically*:

> `${x}` must mean the same thing wherever it is written.

A selector drawn from CLI or file values would be resolved at load time and then merged again, so
a later source overriding it leaves the document saying `prod` while `staging.yaml` is what was
actually loaded — silently. The process environment has no such skew: it is fixed for the life of
the process, so `${env.APP_ENV}` in an include path and in an ordinary value denote the same
value. That is the entire argument for the restriction, and the reason the namespace comes first
and the include path second.

Only the path may carry an expression, and a reference to anything but the namespace there is an
error naming the restriction — never a silent miss.

## Shape

**The values come from the `env` mapping the pipeline already threads**, which defaults to
`os.environ` (`_api.py:107`) and is a parameter of `merge()`, `load()` and all five adapters'
context helpers. Never read `os.environ` inside the engine: the mapping is what makes this
testable, and it is what lets an application pass a filtered environment
([09](../../architecture/09-invariants.md#delegate-to-the-canonical-function)).

**Nothing is materialized.** Do not inject the environment as a node into the merged dict. If it
were data, `merge()` would carry every variable and `dump_file(merge(...))` would write the whole
environment to disk, secrets included. Resolve it lazily instead — the engine takes the mapping as
a namespace — so only referenced names are read, and a dumped merged config keeps `${env.X}`
verbatim and stays portable across environments. This is where `env` differs from `locals`
([08](../../architecture/08-locals.md)): a local *is* data in the document and is stripped at
`build()`; `env` is not data and never enters.

**The name is reserved and derived from the target**, exactly as the locals namespace is: `env`
unless the target owns a real `env` field, in which case `_env`; a target owning both has no
namespace; writing both spellings is an error. Same predicate, same helper shape
([08](../../architecture/08-locals.md#derived-name), `_segment_names_real_field`).

## Two exemptions, both static

The whole implementation turns on these, and both are one-liners *because the name is fixed*:

- `_collect_names` must not emit `env.X` as a dependency edge. There is no such node in the
  document, so the Kahn sort would fail looking for it
  ([07](../../architecture/07-expressions.md#resolution-algorithm)).
- `_Prefixer.visit_Name` must leave `env` alone, beside `_ROOT_ANCHOR`, or a mounted fragment's
  `${env.X}` becomes `${sub.env.X}`
  ([07](../../architecture/07-expressions.md#reference-anchoring),
  [09](../../architecture/09-invariants.md#fragile-couplings)).

This is the same mechanism [FEAT-21](FEAT-21-app-supplied-expression-functions.md) settles on for
application-supplied functions, and the same reason it prefers a reserved namespace to a registry:
a fixed name keeps prefixing correct without the table being visible during `merge()`. Whichever
lands first should build the exemption so the other reuses it.

## Plumbing for the include path

The namespace has to reach file loading, which currently takes paths and nothing else:

`_merge_sources` → `_load_subpath_files` → `_load_file` → `_load_raw` → `_resolve_node` →
`_resolve_dict` / `_resolve_list`, where the path string is evaluated before `_load_includes`.
`_load_cli_config` (`_pipeline.py:64`) reaches `_load_file` too.

One more caller is easy to miss: `_tags.py:52` pre-loads `--config` files straight from argv to
discover union tags before flag registration. It suppresses every exception, so an unresolved
include would degrade rather than crash — but the tag pre-scan would stop seeing an
environment-selected file, and `--help` would list different flags. It must be given the same
mapping.

## Open, to settle before implementing

- **`env_prefix` is `None` by default, deliberately**: environment variables are not a source
  unless the application opts in, because a shared environment is not a safe place to take field
  values from. A namespace that reads arbitrary names sidesteps that, and hands whoever writes a
  config file the ability to lift `${env.AWS_SECRET_ACCESS_KEY}` into a field that is then logged
  or dumped. Reading only the passed mapping mitigates it (an application can filter); gating the
  namespace on `env_prefix is not None`, or requiring the prefix, are the stricter answers. This
  is the decision that should gate the whole ticket.
- **A missing variable** must raise, naming it. Whether there is a spelling for a default is the
  real usability question for `configs/${env.APP_ENV}.yaml`: OmegaConf has `${oc.env:VAR,default}`;
  here the candidates are whitelisting a `get` on the namespace (`_SAFE_METHODS` holds string
  methods only today) or leaving it to the conditional, which lacks a membership test.
- **Types.** Environment values are strings, so `${env.PORT + 1}` concatenates; `${int(env.PORT)}`
  already works. Locals avoided this by requiring a self-describing format, which `env` cannot
  have — document it rather than fix it.

## Not a missing capability

Selecting a file per deployment already works from outside: `--config configs/prod.yaml`,
`MYAPP_CONFIG=configs/prod.yaml` via `env_config`, a `<PREFIX>CONFIG__<SUBPATH>` pointer, or the
application computing the path and passing it in `files=`. What this adds is that a base file
shipped with the application can own the layout, so the invocation does not have to know it —
the same gain Hydra's defaults list exists for.

Precedents: OmegaConf's `${oc.env:VAR}` is the namespace half, with a default argument confarg has
no spelling for. Docker Compose interpolates `${VAR}` from the shell and `.env` across the whole
file before parsing, `env_file:` paths included — the same "one namespace, applied before the
document is understood" model. GitLab CI allows variables in `include:` but only project, group
and instance ones, never job-level; Hydra allows interpolation in the defaults list but only over
defaults-list choices. GitHub Actions forbids expressions in `uses:` and Terraform in a module's
`source`. Ansible's `vars_files` accepts Jinja with no restriction and is a well-known ordering
footgun. Every system that permits this restricts the namespace to something fixed before the
document is parsed; none lets the document choose its own inputs.

Relations: [FEAT-21](FEAT-21-app-supplied-expression-functions.md) shares the reserved-namespace
exemptions; [FEAT-3](FEAT-3-reserved-sentinel-key-registry.md) gains another reserved name;
accepting this removes a line from [11-limitations.md](../../architecture/11-limitations.md) and
changes the caveat in `docs/how-to/derived-values.md` that says an include path cannot be an
expression.
