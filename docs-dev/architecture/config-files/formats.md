# Formats and data files

## Format dispatch and optional dependencies

Formats are chosen by file extension: `.yaml`/`.yml` (PyYAML), `.toml` (stdlib `tomllib`
to read, `tomli_w` to write), `.json` (stdlib), and `.csv`/`.tsv` (stdlib, data only — see
below). Parser libraries are imported lazily and a missing one becomes
`InvalidConfigFileError.missing_library`, keeping confarg zero-dependency
([design decisions](../design-decisions/zero-runtime-dependencies.md#zero-runtime-dependencies)).

One loader table exists: `_LOADERS`, holding a parser per configuration-layer format. Data
formats (`.csv`/`.tsv`) are not in it — data is a value, not a layer — and `_load_document`
routes them to `_load_csv` with their `orient`/`header` options instead. `_load_document` is the
single owner of "read this location and parse it"; `_load_any` is that plus include resolution,
so it is the one function that reads a document. Every mount route goes through it, which is
what keeps the accepted fragment shapes and the per-format options from differing by channel
([mounting](mounting.md#mounting)). A document root additionally answers `_loader_for(loc, _LOADERS)`
first, which is what makes a `.csv` root `unsupported_format` rather than data.

The loaders return the document's **raw** top-level value; no format knows the root rule.
`_require_layer` is the single place that requires a root to be a mapping, so every format,
every `__include__` that rewrites a root and every mount route answer to one check and one
error ([invariants](../invariants.md#delegate-to-the-canonical-function)). Enforcing it after include
resolution rather than at parse time is what lets a root file be nothing but `__include__`.
`_load_raw` is `_load_any` plus that check, plus the one format restriction a *document* root
carries: a data file is a value and not a layer, so `.csv`/`.tsv` is rejected there while
`_load_any` reads it happily at a mounted node.

An **empty** document is the one non-dict root that passes: YAML parses an empty file (and an
explicit `null`) as `None`, which `_require_layer` reads as "contributes nothing" so that an empty
YAML file behaves like an empty TOML one. Every other non-dict root — a list or a scalar —
raises `InvalidConfigFileError.non_dict_root`, because silently loading it as `{}` discards a
file the user asked for and the failure only surfaces much later as a missing field.

## Data files versus configuration layers

A YAML/TOML/JSON file is a **configuration layer**: its keys are structure an author chose,
and it deep-merges. A CSV/TSV file is **data**: it contributes one value.

- CSV carries no types, so every cell is a `_StrToken` and coerces against the target leaf
  type exactly like CLI and env tokens ([types](../types/token-model.md#token-model)).
  Header names are structure, so they stay plain `str`.
- An include of a data file *replaces* earlier include entries instead of merging key-wise:
  under `orient: columns` its keys are column headers, and merging per column would splice
  unrelated tables together.
- Rows must be rectangular only where the result is keyed (`orient: columns`, or `rows` with
  a header); ragged rows are representable as `list[list[str]]` so `raw` and header-less
  `rows` allow them. Blank lines are dropped so they never count as ragged rows.
- Local variables cannot be declared from CSV/TSV: a local has no annotation to coerce
  against ([locals](../locals.md#declare-in-files-modify-anywhere)).
- A data file is reachable from every channel, not only from `__include__`: it contributes a
  value, so any mount route may put it at a node ([mounting](mounting.md#mounting)). Only a *document*
  root refuses it, which is the same rule stated once.
