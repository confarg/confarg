# A scheme handler returns bytes

`confarg.register_scheme(scheme, read)` takes a reader returning **`bytes`**, given the full
location string exactly as the user wrote it. confarg then decodes, per format, in one place.

The alternative — a handler returning decoded `str` — is friendlier to write against an HTTP
client, and was rejected because it hands away a decision the formats disagree about.
`tomllib.loads` requires `str` and `tomllib.load` requires binary, `json.loads` tolerates a BOM
in `bytes` but *raises* on one in `str`, and `csv` needs `utf-8-sig` plus `newline=""` to strip a
BOM without rewriting a CRLF inside a quoted field. With `str`, a handler decoding as plain
`utf-8` silently renames a CSV's first column to `\ufeffname` and breaks BOM'd JSON outright, and
the most familiar HTTP client makes exactly that mistake for you: `requests.Response.text` falls
back to ISO-8859-1 for a `text/*` response carrying no charset, so the obvious three-line handler
mojibakes any non-ASCII configuration. With `bytes` that bug is unwritable.

An open binary file object was the other candidate, and is the smallest diff — `tomllib.load`,
`json.load` and `yaml.safe_load` all take one. Rejected because it puts a resource lifetime into
a public contract and moves errors to the wrong place: a stream can open cleanly and fail
mid-read, so a dropped connection surfaces from inside PyYAML as `Malformed YAML: <url>:
connection reset` rather than as a read failure. Retry or caching would have to buffer it back
into bytes anyway. A lenient `bytes | str` was rejected for leaving the contract permanently
underspecified.

Cost: the four loaders parse from memory rather than streaming, which is irrelevant at
configuration-file sizes.

Precedents, each taking the full URI the way this does: fsspec `register_implementation`,
smart_open `register_transport`, `requests` `Session.mount`, PyFilesystem openers. They hand back
a stream rather than bytes because they are general-purpose file layers; a configuration document
is small and read exactly once.

## The registry can be emptied, and removal is loud

`unregister_scheme(scheme)` is the counterpart, and takes built-ins too. A registry that only
grows has no way to express "this program never reads configuration off the network", and that
needs saying in one place: the location can arrive from `--config`, from `<PREFIX>CONFIG__…`, or
from an `__include__` inside a file that is itself trusted, so a per-channel opt-out would have
to be spelled five times and could still be missed. Dropping `http` and `https` states it once,
and the scheme then takes the same unregistered path as `gs:` — an error naming what remains,
not a filename.

Rejected: a `allow_remote=False` keyword on `load()`/`merge()`, which is the first idea and the
one every front-end would have to carry, for a policy that is a property of the program rather
than of a call — the same argument that made the registry global. Also rejected: leaving removal
out and telling applications to register a reader that raises, which works but makes the error
theirs to word and leaves `confarg.load()` looking as though the scheme were supported.

**Removing what is not registered raises `ValueError`.** The tempting alternative is an
idempotent no-op, as `set.discard` and `dict.pop(k, None)` are. Rejected because the failure it
hides is the one that matters: `unregister_scheme("htp")` would report nothing and leave `http`
loadable, so a program that believes it has closed the network has not. Precedent in the stdlib
is split: `atexit.unregister` and `codecs.unregister` accept anything silently, while
`shutil.unregister_archive_format` and `unregister_unpack_format` raise `KeyError`. The deciding
difference is that here the silent version is unsafe rather than merely quiet. `ValueError`
rather than `shutil`'s `KeyError` because the argument is a name to validate, not a key to look
up — the same error `register_scheme` already raises for a name that cannot be a scheme.
