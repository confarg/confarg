---
filed: 2026-10-15
where:
  - src/confarg/_parse_cli.py::_handle_delete_token
  - src/confarg/_parse_env.py::_handle_env_delete
  - src/confarg/_merge.py::_apply_list_ops
---
# Q-8 — Should a delete on an untyped node be read by its content?

Argv and the environment decide at parse time whether a delete removes an index (`{__delete__: [N]}`) or a key (`DICT_DELETE` at the key), by the type the walk reaches ([collection patches](../../architecture/cli-parsing/collection-patches.md)). Where the type cannot tell, on an `Any`, below a callable's spec, or on a union mixing a sequence and a mapping, a segment spelling an index is an index delete. So `--a.1-` deletes index 1 of an `Any` holding a list, but on an `Any` holding a dict with key `1` (`{1: x}` or `{"1": x}`) it is refused as a list op on a dict, and argv and the environment have no spelling that deletes that key. A file does: `a: {"1": {__unset__: true}}`.

The options weighed while planning BUG-174, and why each was set aside then:

- **A deferred delete**, a third shape the merge resolves against what lies below (a list makes it an index delete, a dict a key delete). A value patch on an `Any` already works this way. It costs an internal marker every reader of ops must know, and `dump_file` has no file spelling for "whichever fits".
- **One shape for both, the key's**, as RFC 6902's `remove` and OmegaConf's `~a.1` are read against the document. Argv and the environment then lose "delete index *i*, then patch what slides into *i*" within one source (`--xs.0- --xs.0 X`), and it partly reverses FEAT-43.
- **One shape for both, `{__delete__: [...]}` in the parent.** It keeps every list chain, but rewrites the key-delete machinery and needs a story for `__unset__` at a fragment's root.

The question is whether the gap is worth any of them, and if so, whether the untyped node alone may use one (the merge knows the node's type through `merge_at`).
