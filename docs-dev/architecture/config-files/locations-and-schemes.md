# Locations and schemes

A configuration source is named by a **location string**, not a `pathlib.Path`: a local path as
before, or a URL — `file:/home/bob/config.yaml`, `https://cfg.example.com/app.yaml`,
`s3://bucket/path/config.yaml`. Every channel names one the same way (`files=`, `env_config`,
`<PREFIX>CONFIG__<SUBPATH>`, `--config[.subpath][+]`, `__include__`), because they all reach
`_files` through one funnel: the scheme is orthogonal to the channel, so nothing had to be
spelled per channel.

`_sources.py` owns the five decisions a location implies, one function each
([invariants](../invariants.md#delegate-to-the-canonical-function)), so `_files.py` never branches on
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
([design decisions](../design-decisions/scheme-handler-returns-bytes.md#a-scheme-handler-returns-bytes)).

**Handlers return `bytes`**, so decoding is one decision per format instead of one per handler
([design decisions](../design-decisions/scheme-handler-returns-bytes.md#a-scheme-handler-returns-bytes)). Reading is also the single place a
failure becomes an `InvalidConfigFileError`, so no loader carries its own `FileNotFoundError`
branch any more.

**Format still comes from the suffix**, with query and fragment stripped first, so
`https://h/app.yaml?env=prod` is YAML. A location with no suffix raises; nothing sniffs content
or reads a `Content-Type`, so every scheme answers the format question identically
([limitations](../limitations.md#remote-sources)).

## Relative includes resolve within one origin

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
([design decisions](../design-decisions/remote-document-same-origin.md#a-remote-document-reaches-only-its-own-origin)).
