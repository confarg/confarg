# Merge ops are markers no channel types

The merged dict records a list op under a key: append, delete, delete-after-append, and the
base list the others apply to. Those keys shared one key space with the user's data, as the
plain strings `+`, `-`, `~` and `*`, so a dict's own key spelled like one was read as the op
(BUG-185, BUG-199) and two layers' values of it were combined as ops instead of replaced. The
merge cannot tell them apart by the value: a dict key `*` may hold a list as a base does.

**The four ops are markers no channel types, and a file writes each by a reserved name.**
`_merge._OpKey` is a `str` subclass whose text is the reserved key (`__append__`, `__delete__`,
`__delete_after__`, `__base__`) and which equals only another marker, never the plain string.
`_normalize_merge_ops` turns a file's reserved key into the marker; a flag, a variable or a mount
point naming one is refused (`_parse_cli._reserved_segment`), as for the other
[file-only keys](../config-files/reserved-keys.md#reserved-file-only-keys); `_serialize_untyped`
writes a marker back as its key, so `dump_file(merge(...))` reads back through
`merge(files=[saved])` as the dict it was. The behavior is in
[deep merge](../pipeline/deep-merge.md#no-channel-types-an-op).

This is the shape the cast already had: a CLI cast is a `_Pinned` in the merged dict, which no
channel types, and it leaves by the file-only `{__cast__, __value__}` spelling
([types](../types/stealing-rule.md#cast-pinning-in-files)). Sentinel objects for "no value" are
Python's own idiom (`dataclasses.MISSING`, PEP 661); MongoDB's update operators (`$push`,
`$pull`) and Kubernetes' strategic merge patch directives (`$patch`, `$retainKeys`) are the
in-band precedent for reserving a spelling, which confarg does for the file channel only.

Why a `str` subclass, not a bare object: every annotation of the merged dict stays
`dict[str, Any]`; an error message, a sorted key list and a construction path spell the marker as
a file does; and the equality is by type and text, not identity, so a `copy.deepcopy` or a pickle
of the merged dict keeps its ops.

What it costs:

- `merge()` returns a dict that can hold keys that are not plain strings, wherever an op waits
  for `build()` (an append with no base, a deferred patch). Its repr shows `'__append__'`.
- Four more reserved keys, and the names in `_defaults.RESERVED_KEYS` are reserved outright: a
  field named like one cannot be set, which [real field wins](real-field-wins.md) does not
  rescue. A file always read `__include__` and `__cast__` as its own; the CLI and the
  environment now refuse them too ([limitations](../limitations.md#collections)).
- `build()` reads the markers, not their spellings: a parsed file handed to it directly applies
  no op, as it applies no `key+:` shorthand. A saved merged dict is read back by `merge()`.

Rejected:

- **Keep the strings and reserve them** — refuse `+`, `-`, `~`, `*` as dict keys on the CLI and
  in the environment, and let files go on writing the ops literally. The smallest change, and
  the merged dict stays plain JSON, but the file channel keeps the collision: two files giving a
  dict key `+` still append, and a file's `*` still wipes a dict. JSON Merge Patch (RFC 7396)
  is the cautionary precedent for in-band markers on every channel: its `null` deletes, so no
  patch can set a value to `null`.
- **Markers with no file spelling** — `dump_file` would write the append and the delete through
  the user shorthands (`key+:`, `"N-":`) and refuse a merged dict carrying a base or a
  post-append delete. No new reserved key, but `dump_file(merge(...))` would fail for an ordinary
  `--pt.x 9` over a file's `pt: [1, 2]`, which it wrote until then.
- **Escape a user's key that looks like an op** — every channel would rewrite `*` to some escaped
  form and `build()` would unescape it. A second spelling of every such key in the merged dict,
  and in every message and dump that shows it.
- **An out-of-band op stream** — record the ops beside the dict instead of in it, as JSON Patch
  (RFC 6902) does. It answers more than this question, and is
  [FEAT-4](../../todo/features/FEAT-4-ordered-patch-op-stream.md)'s to decide.
- **Symbolic names** (`__+__`, `__*__`) for the file spelling — they keep today's vocabulary
  recognisable, but a dumped file reads better with the op named.
