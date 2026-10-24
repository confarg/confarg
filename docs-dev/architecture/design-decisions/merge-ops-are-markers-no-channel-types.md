# Merge ops are markers no channel types

The merged dict records a list op under a key: append, delete, delete-after-append, and the base list the others apply to.
Those keys shared one key space with the user's data, as the plain strings `+`, `-`, `~` and `*`, so a dict's own key spelled like one was read as the op (BUG-185, BUG-199) and two layers' values of it were combined as ops instead of replaced.
The merge cannot tell them apart by the value: a dict key `*` may hold a list as a base does.

**The four ops are markers no channel types, and a file writes each by a reserved name.**
`confarg.ListOp` is an `enum.Enum` (defined in `_merge`) whose members' values are the reserved keys (`__append__`, `__delete__`, `__delete_after__`, `__base__`); no string equals a member.
`_read_file_ops` turns a file's reserved key into the marker; a flag, a variable or a mount point naming one is refused (`_parse_cli._reserved_segment`), as for the other [file-only keys](../config-files/reserved-keys.md#reserved-file-only-keys); `_serialize_untyped` writes a marker back as its key, so `dump_file(merge(...))` reads back through `merge(files=[saved])` as the dict it was.
The behavior is in [deep merge](../pipeline/deep-merge.md#no-channel-types-an-op).

This is the shape the cast already had: a CLI cast is a `_Pinned` in the merged dict, which no channel types, and it leaves by the file-only `{__cast__, __value__}` spelling ([types](../types/stealing-rule.md#cast-pinning-in-files)).
Sentinel objects for "no value" are Python's own idiom (`dataclasses.MISSING`, PEP 661); MongoDB's update operators (`$push`, `$pull`) and Kubernetes' strategic merge patch directives (`$patch`, `$retainKeys`) are the in-band precedent for reserving a spelling, which confarg does for the file channel only.

## Why an enum, and why a public one

A marker is a key of a type of its own, so no code can take one for a string: `isinstance(k, str)` is false of it, and a string method, `int()` or a `".".join` over it fails loudly rather than reading `__append__` as a field name.
The merged dict is typed accordingly, `MergeDict = dict[str | ListOp, Any]`, from every channel's parse result to the expression engine and construction, so the type checker names every place that assumes a key is text.

`merge()` returns that dict, and `build()`, `resolve()` and `dump_file()` take it back, so the marker's type is in a public signature: `merge()` is annotated `dict[str | ListOp, Any]`, and the inputs `dict[Any, Any]`, so a caller's own `dict[str, int]` passes as well (`dict` is invariant in its key type, and the functions require an actual dict, not any mapping).
That makes the type public as `confarg.ListOp`, for a caller to recognise a pending op in what `merge()` returned, as `dataclasses.MISSING` is public for a caller to recognise a missing default.

`str()` of a member is its reserved key, which is how messages and dumps spell it, as a file writes it.
`repr()` is the short qualified name, `ListOp.APPEND`, so a printed merged dict shows a pending op as code a caller can paste back (`{'xs': {ListOp.APPEND: [3]}}`) and never as a string a user could have typed; `re`'s flags print the same way (`re.IGNORECASE`).
The enum's members are singletons, so a `copy.deepcopy` or a pickle of the merged dict keeps its ops.

A position in the data may cross a pending op: an expression inside an appended item sits at `("servers", ListOp.APPEND, "0", "url")`.
The expression engine takes the marker as a segment of its own: a node anchor (`${.host}`) reads through it, and a message spells it as a file writes it ([expressions](../expressions/values-and-references.md#a-position-is-a-sequence-of-segments)).

What it costs:

- `merge()` returns a dict that can hold keys that are not strings, wherever an op waits for `build()` (an append with no base, a deferred patch), and a public name for their type.
- Every function on the merged dict's path is annotated `MergeDict`; a test that calls one with a plain dict literal annotates it so, as `dict[str, X]` is not a `MergeDict`.
- Four more reserved keys, and the names in `_defaults.RESERVED_KEYS` are reserved outright: a field named like one cannot be set, which [real field wins](real-field-wins.md) does not rescue.
  A file always read `__include__` and `__cast__` as its own; the CLI and the environment now refuse them too ([limitations](../limitations.md#collections)).
- `build()` reads the markers, not their spellings: a parsed file handed to it directly applies no op, its reserved keys being plain strings there, which construction refuses.
  A saved merged dict is read back by `merge()`.

Rejected:

- **A `str` subclass equal only to another marker** — what FEAT-3 first built.
  It kept every annotation `dict[str, Any]` and let a marker pass for its reserved key wherever text was expected, but it was a string for `isinstance`, string methods, `json.dumps` and `int()`, and not for `==` and hashing.
  Code that walked the merged dict's keys read a marker as the field `__append__` without a sound: the locals walkers did, which hid BUG-219 ([locals](../locals.md#a-namespace-in-an-item-a-list-op-holds)), and `k in MERGE_OP_KEYS` read as "is this an op" while it matched only the plain spelling.
  Swapping it for the enum failed loudly at exactly those places.
- **A bare sentinel object per op** — what the enum is, with the iteration, the lookup by value and the pickling `enum` already provides.
- **Keep the strings and reserve them** — refuse `+`, `-`, `~`, `*` as dict keys on the CLI and in the environment, and let files go on writing the ops literally.
  The smallest change, and the merged dict stays plain JSON, but the file channel keeps the collision: two files giving a dict key `+` still append, and a file's `*` still wipes a dict.
  JSON Merge Patch (RFC 7396) is the cautionary precedent for in-band markers on every channel: its `null` deletes, so no patch can set a value to `null`.
- **Markers with no file spelling** — `dump_file` would write the append and the delete through the file shorthands of the time (`key+:`, `"N-":`, which FEAT-43 later made data) and refuse a merged dict carrying a base or a post-append delete.
  No new reserved key, but `dump_file(merge(...))` would fail for an ordinary `--pt.x 9` over a file's `pt: [1, 2]`, which it wrote until then.
- **Escape a user's key that looks like an op** — every channel would rewrite `*` to some escaped form and `build()` would unescape it.
  A second spelling of every such key in the merged dict, and in every message and dump that shows it.
- **An out-of-band op stream** — record the ops beside the dict instead of in it, as JSON Patch (RFC 6902) does.
  It answers more than this question, and is [FEAT-4](../../todo/features/FEAT-4-ordered-patch-op-stream.md)'s to decide.
- **Symbolic names** (`__+__`, `__*__`) for the file spelling — they keep today's vocabulary recognisable, but a dumped file reads better with the op named.
- **The enum's default `repr`** (`<ListOp.APPEND: '__append__'>`) — it shows the file spelling, which `str()` already gives every message and dump, at the cost of a printed merged dict that reads as no code.
