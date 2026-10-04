# Mounting

Three routes put a document's root at an arbitrary path of the merged document:
`__include__` under a key, `--config.<subpath>`, and `<PREFIX>CONFIG__<SUBPATH>`. A document
never needs to know where it will be mounted. Consequences handled at mount time:
expression references are prefixed ([expressions](../expressions/reference-anchoring.md#reference-anchoring)) and a
`locals:` block lands wherever the root lands ([locals](../locals.md#per-node-namespaces)).

The three spell the keyword and carry the path differently — a dotted flag suffix against
structural nesting — and that divergence is argued in
[design decisions](../design-decisions/mount-keyword-per-channel.md#the-mount-keyword-is-spelled-per-channel). What they *mount* does
not diverge. `_load_mount_value` reads a `--config[.<path>]` token or a `CONFIG[__PATH]`
variable as an `__include__` value, so all three accept the same locations, the same
`{path: …, orient: …}` object (spelled as JSON on argv and in the environment) and the same
list form, and `_load_mount` is the one implementation of "put this value at that subpath": it
loads the value with the subpath as its *mount*, so references are anchored as the documents
load ([expressions](../expressions/reference-anchoring.md#a-document-is-prefixed-once-by-its-whole-mount-path)),
then nests it. `_load_any` is the one loader underneath all of it.

Two things do differ, both on purpose:

- **Where a relative location starts.** `__include__` resolves against the including
  document — its own directory locally, its own origin and path remotely
  ([relative includes resolve within one origin](locations-and-schemes.md#relative-includes-resolve-within-one-origin))
  — because the document naming it is the thing that knows where it sits; the CLI and the
  environment have no including document and resolve against the process working directory,
  because that is what the person typing the flag means. `_sources._join` carries both: the
  base is the including document, or `None` for these routes.
- **What the root may be.** An empty subpath is a document root and must be a configuration
  layer, so `_require_layer` applies and a data file is refused there. A non-empty subpath is a
  node, where — exactly as for a pure `__include__` — the value may be a list, a scalar or a
  CSV.
- **Whether the subpath is checked.** The two flag routes name a node from *outside* the
  document, so each checks its subpath against the target at interception
  (`_parse_cli._check_mount_subpath`, one canonical walk for vanilla's scan, the adapters'
  rescan and the environment's config handler): a subpath that names no node is an error at
  parse time, not a silent mount at an invented key that surfaces much later as an
  unknown-field error from `build()` (BUG-50, closed). A file's mount key is a node the file
  author wrote, so the file route has nothing to intercept — the same mistake there is data,
  and `build()` is what reports it.

One consequence is not yet handled: an appended fragment (`--config.<path>+`) keeps its bare
references anchored at the merged root rather than at the element it lands on, because that
element has no index until the merge is over ([limitations](../limitations.md)).
