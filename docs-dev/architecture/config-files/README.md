# Config files

The lowest-priority channel: where a document is read from, how it is parsed, and how one
document splices another. Implementation: `_files.py`, `_sources.py`.

The other file-shaped channel, environment variables, is
[environment-parsing.md](../environment-parsing.md).

| Note | What it holds |
|---|---|
| [locations-and-schemes.md](locations-and-schemes.md) | a location is a path *or* a URL; the scheme registry, and why a remote document reaches only its own origin |
| [formats.md](formats.md) | extension-driven format dispatch, optional parser libraries, and the configuration-layer/data-file split |
| [include-semantics.md](include-semantics.md) | what `__include__` accepts, what it yields, and how it composes |
| [mounting.md](mounting.md) | the three routes that put a document's root at an arbitrary path, and where they may differ |
| [reserved-keys.md](reserved-keys.md) | the dunder keys only a file can spell, and why that is structural |
