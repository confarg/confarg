# Config files and environment variables

## Format dispatch and optional dependencies

Formats are chosen by file extension: `.yaml`/`.yml` (PyYAML), `.toml` (stdlib `tomllib`
to read, `tomli_w` to write), `.json` (stdlib), and `.csv`/`.tsv` (stdlib, data only — see
below). Parser libraries are imported lazily and a missing one becomes
`InvalidConfigFileError.missing_library`, keeping confarg zero-dependency
([10-design-decisions.md](10-design-decisions.md#zero-runtime-dependencies)).

Two loader tables exist: `_LOADERS` (a root configuration layer, must be a dict) and
`_ITEM_LOADERS` (any top-level value, used by `__include__` and `--config.<path>+`, where a
list or scalar root is meaningful).

## Data files versus configuration layers

A YAML/TOML/JSON file is a **configuration layer**: its keys are structure an author chose,
and it deep-merges. A CSV/TSV file is **data**: it contributes one value.

- CSV carries no types, so every cell is a `_StrToken` and coerces against the target leaf
  type exactly like CLI and env tokens ([05](05-types-and-construction.md#token-model)).
  Header names are structure, so they stay plain `str`.
- An include of a data file *replaces* earlier include entries instead of merging key-wise:
  under `orient: columns` its keys are column headers, and merging per column would splice
  unrelated tables together.
- Rows must be rectangular only where the result is keyed (`orient: columns`, or `rows` with
  a header); ragged rows are representable as `list[list[str]]` so `raw` and header-less
  `rows` allow them. Blank lines are dropped so they never count as ragged rows.
- Local variables cannot be declared from CSV/TSV: a local has no annotation to coerce
  against ([08-locals.md](08-locals.md#declare-in-files-modify-anywhere)).

## Include semantics

`__include__` accepts a path, a `{path: …, <format options>}` dict, or a list of either.

- Paths are relative to the including file's directory.
- A list is layered left to right into one value first, so the list form means the same in a
  dict node and in a list item. Dict entries deep-merge, mirroring repeated `--config`.
- A pure include (no sibling keys) may yield any type; with siblings the include must yield a
  dict, and siblings merge on top (they were written by the including file).
- In a list, an include yielding a list is spliced in.
- Cycle detection: `seen` grows **per entry**, not across a list. Sibling entries are
  sequential layers, not nesting, so naming the same file twice is legal while a genuine
  cycle still raises.

## Mounting

Three routes put a file's root at an arbitrary path of the merged document:
`__include__` under a key, `--config.<subpath>`, and `<PREFIX>CONFIG__<SUBPATH>`. A file
never needs to know where it will be mounted. Consequences handled at mount time:
expression references are prefixed ([07](07-expressions.md#reference-anchoring)) and a
`locals:` block lands wherever the root lands ([08](08-locals.md#per-node-namespaces)).

## Reserved file-only keys

`__include__`, `__root__` (value of a non-struct target) and `__cast__`/`__value__`
([05](05-types-and-construction.md#cast-pinning-in-files)) are dunder keys and are file-only
by construction: the default env separator is also `__`, so a dunder name cannot be written
as an environment variable. Anything that must work in every channel (such as the locals
namespace) therefore avoids the dunder form.

## Environment parsing

- **Disabled by default** (`env_prefix=None`); see
  [10](10-design-decisions.md#environment-variables-off-by-default).
- The separator defaults to `__` so single underscores stay usable in field names
  (`MYAPP_DB__MAX_CONNECTIONS` → `db.max_connections`).
- Segments are matched **case-insensitively** against the target type tree, because env
  names are conventionally upper-case; a segment matching several fields is an error.
- Values starting with `[` or `{` are parsed as JSON only when the target type can accept a
  list or an object; otherwise they are ordinary tokens.
- `<PREFIX>…__json` mirrors the CLI `.json` cast, including "real field wins" and a hard
  error on invalid JSON.
- `FOO__BAR-` / `FOO__ITEMS__1-` are deletes, mirroring `--bar-` / `--items.1-`.
- `<PREFIX>CONFIG[__SUBPATH]` are file pointers, collected and loaded by the pipeline. The
  variable named by `env_config` is removed from field parsing.
- An unknown first segment emits `ConfargWarning` and the variable is ignored, whereas an
  unknown CLI flag is an error. *(inferred)* The environment is ambient and shared with
  other software, while argv is an explicit request; a stray variable should not stop the
  program. Tests can escalate the warning with `warnings.filterwarnings("error", …)`.
