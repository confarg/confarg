# confarg architecture notes

Internal notes for contributors and coding agents, part of [`docs-dev/`](../README.md).
They are deliberately **not** published: they name private symbols, carry *(inferred)*
rationale, open questions and known deviations from the intended behavior. Publishing them
(for instance as an "Internals" section copied into the site at build time, the way
`examples/` is) is to be reconsidered once the library ships.

These documents are the **single source of truth for the "why"**: design choices,
rationale, rejected alternatives, trade-offs and limitations. The code and its docstrings
describe *what* things do; they must not repeat the reasoning kept here. When a rationale
changes, change it here.

Work that is still *open* — bugs, missing features, refactors, questions for the
maintainer — lives on the boards in [`../todo/`](../todo/README.md), not in these notes. A
ticket describes work to do; closing it usually leaves a decision, and the decision comes
back here.

## How to use these notes

1. Read this file, then [09-invariants.md](09-invariants.md) before changing anything.
2. Open only the topic documents that match the code you are touching (table below).
3. Docstrings point here through an `Agent Notes:` section, e.g.

   ```python
   def _try_coerce(ft, token):
       """Coerce a string token to the target type if unambiguous.

       Agent Notes:
           docs-dev/architecture/07-expressions.md#deferral-rule
       """
   ```

   The section is hidden on the documentation site by `docs/assets/stylesheets/extra.css`
   (mkdocstrings renders it as `<details class="agent-notes">`). Cite a document and an
   `##` heading anchor; headings in these files are kept stable for that reason.
4. Rationale marked *(inferred)* was reconstructed from the code, not stated by the
   maintainer. Treat it as a hypothesis and confirm before relying on it.

## Reading guide

| If you touch… | Read |
|---|---|
| `_api.py`, `_pipeline.py`, `_merge.py` | [01-pipeline-and-contracts.md](01-pipeline-and-contracts.md) |
| `_files.py`, `_parse_env.py` | [02-files-and-env.md](02-files-and-env.md) |
| `_parse_cli.py`, `_cast.py` | [03-cli-parsing.md](03-cli-parsing.md) |
| `cli/**` | [04-cli-adapters.md](04-cli-adapters.md) (and 03) |
| `_types.py`, `typedload/**`, `_serialize.py`, `_import.py` | [05-types-and-construction.md](05-types-and-construction.md) |
| `_callable.py`, anything `Callable`-typed | [06-callables.md](06-callables.md) |
| `dictexpr/**`, any value gate that runs before `build()` | [07-expressions.md](07-expressions.md) |
| anything mentioning `locals` / `_locals` | [08-locals.md](08-locals.md) |
| a new feature or public behavior | [10-design-decisions.md](10-design-decisions.md), [11-limitations.md](11-limitations.md), and the boards in [../todo/](../todo/README.md) |
| tests | [12-testing.md](12-testing.md) |

## Vocabulary

- **Channel** (or input type): config files, environment variables, command-line arguments.
- **Front-end**: vanilla `confarg.load()`/`merge()`, and the argparse, click and cyclopts
  adapters. Four front-ends × three channels must behave identically.
- **Merged dict / raw dict**: the plain nested `dict` produced by `merge()`, expressions
  still literal.
- **Token**: a string from a channel that carries no types (`_StrToken`), eligible for
  coercion to the target type.
- **Leaf**: a scalar-like value (bool, int, float, str, None, Literal, Enum, `type[X]`, or a
  registered leaf type such as `Path`). **Struct**: a dataclass, or a plain class whose
  `__init__` takes parameters.
- **Mounting**: placing a configuration file's root at some path of the merged document
  (`__include__`, `--config.<path>`, `CONFIG__<PATH>`).
- **Value gate**: any code that inspects or converts a value before `build()` runs.

## Source map

Dependencies flow downwards: the public API uses the pipeline, the pipeline uses the
parsers and the merge core, and the two engines at the bottom (`typedload`, `dictexpr`)
know nothing about channels. `dictexpr` imports only the standard library and
`confarg.exceptions`.

```
confarg/
├── __init__.py        public surface; register_leaf_type
├── _api.py            load / merge / build / from_dict / resolve / dump / dump_file
├── _defaults.py       shared keyword defaults (always reference, never repeat literals)
├── exceptions.py      ConfargError hierarchy, ConfargWarning
│
│   channels
├── _parse_cli.py      argv → nested dict (type-guided); --config scan; patch-only mode
├── _parse_env.py      env → nested dict; CONFIG__* pointers
├── _files.py          load/dump by extension; __include__; CSV/TSV
├── _cast.py           force-cast table (.str/.int/.float/.bool/.json)
│
│   merge core
├── _pipeline.py       _merge_sources: the one merge-order implementation; locals checks
├── _merge.py          _deep_merge and list/dict patch sentinels
│
│   type machinery
├── _types.py          type introspection; _StrToken, _UnionSeqToken, _Pinned
├── _callable.py       Callable specs (fn/class/call/bind), serialization of callables
├── _import.py         dotted-path import with builtins fallback
├── _serialize.py      typed object → dict (inverse of construction)
├── typedload/         resolved dict → typed object; leaf coercion and registry
├── dictexpr/          ${...} parsing, safety check, evaluation, reference anchoring
│
│   CLI adapters
└── cli/
    ├── _collect.py    flat {dotted.flag: value} → nested dict (shared by all adapters)
    ├── argparse/      _spec (FlagSpec, FieldMeta), _build (framework-neutral spec
    │                  generation, used by every adapter), _register, _namespace, _completion
    ├── click/         _register, _context, _completion
    └── cyclopts/      _register, _context
```
