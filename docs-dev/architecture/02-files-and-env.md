# Config files and environment variables

## Locations and schemes

A configuration source is named by a **location string**, not a `pathlib.Path`: a local path as
before, or a URL — `file:/home/bob/config.yaml`, `https://cfg.example.com/app.yaml`,
`s3://bucket/path/config.yaml`. Every channel names one the same way (`files=`, `env_config`,
`<PREFIX>CONFIG__<SUBPATH>`, `--config[.subpath][+]`, `__include__`), because they all reach
`_files` through one funnel: the scheme is orthogonal to the channel, so nothing had to be
spelled per channel.

`_sources.py` owns the five decisions a location implies, one function each
([09](09-invariants.md#delegate-to-the-canonical-function)), so `_files.py` never branches on
whether a document is local or remote:

| Decision | Function | Local | Remote |
|---|---|---|---|
| which scheme? | `_scheme_of` | `""` | the registered scheme name |
| what bytes? | `_read_bytes` | `Path.read_bytes` | the registered reader |
| which format? | `_suffix` | `Path.suffix` | suffix of the URL path |
| what does a relative include name? | `_join` | `(parent / rel).resolve()` | same origin, path joined |
| the same document? | `_identity` | `Path.resolve()` | the location, fragment stripped |

**A scheme needs two characters.** `C:\Users\bob\config.yaml` is a Windows path, but `urlsplit`
reads its drive letter as a scheme, so a location counts as a URL only when at least two
characters precede the colon. The cost is that a *relative* filename whose first segment contains
a colon (`weird:name.yaml`) reads as a scheme and must be written `./weird:name.yaml`.

**An unregistered scheme is an error, not a path.** `gs://bucket/app.yaml` with no `gs` handler
raises `InvalidConfigFileError.unknown_scheme`, naming what is registered. Falling back to a
filename would report "Config file not found: gs://bucket/app.yaml", sending the reader after a
typo instead of a missing handler.

**The registry is writable both ways.** `register_scheme` adds a reader or replaces one, and
`unregister_scheme` removes one, built-ins included; both normalize the scheme name through
`_normalize_scheme`, so `"HTTP"`, `"http:"` and `"http://"` name one entry wherever they
arrive. Removal exists because a registry that only grows offers no way to say "this program
never reads configuration off the network": dropping `http` and `https` says it once, for every
channel, and a location naming them afterwards takes the unregistered-scheme path above.
Removing an absent scheme raises `ValueError` rather than passing silently, since the usual
cause is a misspelling and silence would leave the real scheme loadable
([10](10-design-decisions.md#a-scheme-handler-returns-bytes)).

**Handlers return `bytes`**, so decoding is one decision per format instead of one per handler
([10](10-design-decisions.md#a-scheme-handler-returns-bytes)). Reading is also the single place a
failure becomes an `InvalidConfigFileError`, so no loader carries its own `FileNotFoundError`
branch any more.

**Format still comes from the suffix**, with query and fragment stripped first, so
`https://h/app.yaml?env=prod` is YAML. A location with no suffix raises; nothing sniffs content
or reads a `Content-Type`, so every scheme answers the format question identically
([11](11-limitations.md#remote-sources)).

### Relative includes resolve within one origin

A relative `__include__` in a remote document resolves against that document's own location,
keeping scheme and netloc and joining the path with `posixpath`. **Not** `urljoin`: it resolves
relatives only for the schemes in `urllib.parse.uses_relative`, so
`urljoin("s3://bucket/env/app.yaml", "db.yaml")` returns `"db.yaml"` with the base silently
discarded. A `posixpath` join gives answers identical to `urljoin` for `http`/`https` and correct
ones for `s3` and for any scheme a user registers.

A remote document may reach only its **own origin**: an include naming another scheme or host —
a local path included — raises `InvalidConfigFileError.cross_origin_include`. Joining by path
makes that structural rather than a check to remember, so a config URL is not a primitive for
reading local files or probing an internal network. The reverse is allowed: a local file may
include any registered location, because whoever wrote it is whoever runs the program
([10](10-design-decisions.md#a-remote-document-reaches-only-its-own-origin)).

## Format dispatch and optional dependencies

Formats are chosen by file extension: `.yaml`/`.yml` (PyYAML), `.toml` (stdlib `tomllib`
to read, `tomli_w` to write), `.json` (stdlib), and `.csv`/`.tsv` (stdlib, data only — see
below). Parser libraries are imported lazily and a missing one becomes
`InvalidConfigFileError.missing_library`, keeping confarg zero-dependency
([10-design-decisions.md](10-design-decisions.md#zero-runtime-dependencies)).

One loader table exists: `_LOADERS`, holding a parser per configuration-layer format. Data
formats (`.csv`/`.tsv`) are not in it — data is a value, not a layer — and `_load_document`
routes them to `_load_csv` with their `orient`/`header` options instead. `_load_document` is
the single owner of "read this location and parse it", so `__include__`, `--config.<path>+`
and a root file all reach one function; a root additionally answers `_loader_for(loc,
_LOADERS)` first, which is what makes a `.csv` root `unsupported_format` rather than data.

The table returns the file's **raw** top-level value; no format knows the root rule.
`_load_raw` is the single place that requires a root to be a mapping, so all three formats and
anything `__include__` rewrites the root to produce one error
([09](09-invariants.md#delegate-to-the-canonical-function)). Enforcing it after include
resolution rather than at parse time is what lets a root file be nothing but `__include__`.

An **empty** document is the one non-dict root that passes: YAML parses an empty file (and an
explicit `null`) as `None`, which `_load_raw` reads as "contributes nothing" so that an empty
YAML file behaves like an empty TOML one. Every other non-dict root — a list or a scalar —
raises `InvalidConfigFileError.non_dict_root`, because silently loading it as `{}` discards a
file the user asked for and the failure only surfaces much later as a missing field.

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

- Paths are relative to the including document's own location, local or remote
  ([above](#relative-includes-resolve-within-one-origin)).
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
  list or an object; otherwise they are ordinary tokens. Optionality does not change the
  answer — `dict[str, str] | None` decodes what `dict[str, str]` decodes
  ([10](10-design-decisions.md#optionality-does-not-change-what-a-whole-value-accepts)).
- `<PREFIX>…__json` mirrors the CLI `.json` cast, including "real field wins" and a hard
  error on invalid JSON. `<PREFIX>JSON` is the root form: it injects a whole config, folded
  in **under** the per-field env vars exactly as root `--json` sits under the field flags
  ([03](03-cli-parsing.md#force-casts)). Whether a trailing `json` is a cast at all is
  decided by the canonical `detect_force_cast`, not by a second rule in `_parse_env`.
- `FOO__BAR-` / `FOO__ITEMS__1-` are deletes, mirroring `--bar-` / `--items.1-`.
- `<PREFIX>CONFIG[__SUBPATH]` are file pointers, collected and loaded by the pipeline. The
  variable named by `env_config` is removed from field parsing.
- An unknown first segment emits `ConfargWarning` and the variable is ignored, whereas an
  unknown CLI flag is an error. *(inferred)* The environment is ambient and shared with
  other software, while argv is an explicit request; a stray variable should not stop the
  program. Tests can escalate the warning with `warnings.filterwarnings("error", …)`.
