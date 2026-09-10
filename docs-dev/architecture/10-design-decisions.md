# Design decisions

Each entry: the decision, why, and what it costs. Precedents are cited where known.

## No custom types required

Plain dataclasses, NamedTuples, plain classes, unions and standard annotations work with no
base class, decorator or field marker; confarg is "not a framework" and its footprint in user
code is a few lines. Break this only for important features that cannot be done otherwise.

- Cost: all knowledge comes from runtime introspection, concentrating complexity in `_types.py`
  and `typedload`. Per-field extras (help, metavar) ride on `Annotated[T, FieldMeta(...)]`, which
  is stdlib and invisible at runtime.
- Precedents: pydantic-settings and Hydra structured configs require their own base classes or
  containers; jsonargparse and cyclopts also introspect plain signatures/dataclasses.

## Plain dicts between stages

See [01](01-pipeline-and-contracts.md#plain-dicts-as-the-intermediate-representation).
Precedents: pydantic-settings and Dynaconf merge mappings before validation; OmegaConf keeps its
own `DictConfig` container. A *plain* dict keeps confarg dependency-free and decomposable.

## One merge pipeline for every front-end

See [01](01-pipeline-and-contracts.md#the-single-merge-pipeline). Cost: adapters must translate
each framework's parse result into confarg's shape, which is where the intricate code lives
(dual parse for patch parity).

## Adapters instead of an own CLI framework

Users keep argparse/click/cyclopts; confarg also parses argv itself, so no CLI library is
needed. Help for large, dynamic configurations is inevitably long and incomplete (derived
classes' fields are unknown until selected), and configuration files are the primary
interface, so a rich CLI UX is a secondary goal.

## union_tag defaults to "class"

`class` is a Python keyword, so no dataclass field can ever be named `class`: the
discriminator can never collide with user data. `type` was rejected as a common field name.
Configurable per call. Cost: unusual for users expecting `type`, and reads slightly oddly in
files. Precedent: Hydra uses a reserved `_target_` key for the same reason.

## Environment variables off by default

`env_prefix=None` disables env parsing. Environment variables are global and shared by every
process, so reading them without an explicit, app-specific prefix is unsafe in shared
environments; `""` (read all) is opt-in, not the default. Cost: one extra argument for the
common case. Precedent: pydantic-settings and Dynaconf both scope by prefix.

## Double underscore separator

`__` splits nesting so single underscores remain usable in names. Precedents:
pydantic-settings `env_nested_delimiter="__"`, Dynaconf `__`. Side effect: dunder keys cannot be
expressed in env ([02](02-files-and-env.md#reserved-file-only-keys)).

## Explicit boolean values

Booleans take a value (`--verbose true`), not `--flag`/`--no-flag`. A bool then behaves like
every other scalar in every channel, with no special parsing or merge rule, and a CLI value can
override a file value in either direction. Cost: less idiomatic for CLI-only users. Precedent:
jsonargparse accepts explicit `true/false` values.

## Zero runtime dependencies

YAML, TOML writing, completion and the CLI adapters are optional; missing libraries produce a
clear install hint. Cost: features depend on extras being installed.

## Expressions resolved after merging, by a whitelisted interpreter

Late resolution lets any channel override an input of a file-defined formula
([07](07-expressions.md#resolution-algorithm)). A small AST interpreter avoids `eval` on
untrusted configuration while covering arithmetic, conditionals and string methods. Precedents:
OmegaConf interpolation resolves lazily with registered resolvers; confarg instead offers a fixed
safe subset of Python syntax.

## A class tag replaces, not merges

A dict carrying the union tag discards the previous value during merge
([01](01-pipeline-and-contracts.md#deep-merge-semantics)), so switching variants does not
inherit the old variant's fields.

## Real field wins over reserved words

Reserved names (casts, locals) are only reserved where they would not shadow a real member, so
confarg never forbids a field name ([03](03-cli-parsing.md#real-field-wins)).

## Strict CLI, lenient environment

Unknown CLI flags are errors, unknown env variables only warn
([02](02-files-and-env.md#environment-parsing)).

## allow_abbrev disabled

`make_parser` sets `allow_abbrev=False`: with abbreviations, adding a field can silently change
which flag an abbreviated invocation means.

## Stealing rule for text in unions

Text is converted to the most specific type that accepts it, with `str` last, but only for
untyped channels ([05](05-types-and-construction.md#stealing-rule)). Coercion happens only when
the target type allows it, so this is not the YAML "Norway problem".
