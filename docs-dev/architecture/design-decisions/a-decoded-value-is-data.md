# A decoded value is data

A file spells a merge op in a key: `name-:` deletes, `xs+:` appends, `"0-":` deletes an index, and the reserved `__append__`, `__delete__`, `__delete_after__` and `__base__` write the ops by name ([deep merge](../pipeline/deep-merge.md#deep-merge-semantics)). Argv and the environment decode JSON too: the `.json` cast (`--sec.json`, `APP_SEC__JSON`), the root cast (`--json`, `APP_JSON`), a whole-value flag or variable (`--d '{…}'`, `APP_D='{…}'`), an item appended as JSON (`--rows+ '{…}'`). Every merge used to read the suffixes and the reserved keys of whatever it merged, so a decoded object read them too, but only where the merge met it: `--sec.json '{"a-": null}'` deleted the file's `sec.a`, while `--json '{"name-": null}'` spent its delete on the objects of the root cast's own fold and the file's `name` came back (BUG-228). A dict field could never receive a key ending in `+` or `-` from any channel.

**A value argv or the environment decodes is data. Only a file's keys spell a merge op.** `{"a-": null}` in a decoded value is the key `a-`: a dict holds it beside its other keys, an `Any` holds it, and a struct refuses it as the unknown field it is, as it would a misspelled one. The ops stay on the path side, where every channel already spells them: `--sec.a-`, `APP_SEC__A-`, `--xs+`, `APP_XS+`. A key confarg reserves is refused in a decoded value as it is on a flag's or a variable's path, with the same message: it has no use as data, and a user writing `__append__` or `__include__` in JSON meant the op or the include.

This is the way to give a dict a key ending in `+` or `-`: a JSON value on argv or in the environment (`--d '{"c++": 1}'`, `APP_D='{"c++": 1}'`), or `build()` from Python. A dict field has no `.json` cast, since `json` is one of its keys there ([real field wins](real-field-wins.md)): its whole value, or its parent's cast, carries such a key. A configuration file cannot hold one ([limitations](../limitations.md#collections)).

## How it is built

- `_cast.decode_json` is the one decoder of a channel's JSON value: every decode site of argv and the environment goes through it, and it refuses a reserved key at any depth of the value, a list's items included.
- `_merge._normalize_merge_ops` reads the keys of one dict, and only `_files._resolve_dict` calls it, on each dict of a configuration document as the include walk leaves it, its values resolved first. So `xs+: {__include__: rows.yaml}` appends the included items, and a delete beside an include deletes in it. No merge reads a key as an op.
- A dict is read once. Reading is not idempotent: `a--:` reads as a delete of the key `a-`, which a second reading would make a delete of `a`. While every merge read both its sides, a file's dict was read once per layer it crossed.
- A data file's header is data too: a CSV column named `k-` is a column, as the file is a value rather than a layer ([formats](../config-files/formats.md#data-files-versus-configuration-layers)).

## Precedents

Hydra parses its override grammar (`+key`, `~key`, `++key`) on the key side of a command-line override only, and a value, a dict included, is data. OmegaConf never reads a YAML key as an op at all; its merges are configured per call. Kubernetes' strategic merge patch reserves its directives (`$patch`, `$retainKeys`) and gives data no way to use their keys, as confarg does with its reserved keys. JSON Merge Patch (RFC 7396) is the cautionary precedent for an op spelled in band on every channel: its `null` deletes, so no patch can set a member to `null`, which it accepts as a limitation.

## What it costs

- `--json '{"xs+": [9]}'` and `APP_JSON='{"xs+": [9]}'` no longer append. The CLI spells it `--xs+ 9`, and the environment `APP_XS+=9` since FEAT-18, whose root variable the root cast had been the only way around.
- A pin, `{"__cast__": "int", "__value__": "5"}`, no longer resolves in a decoded value: it is refused with the other reserved keys. The scalar casts say the same on the path (`--x.int 5`), and JSON types its own scalars.
- No file can hold a key ending in `+` or `-`, nor a reserved key, so a configuration that holds one does not survive a `dump_file` and a reload.

## Rejected

- **A cast is a file's document in one token.** The shorthand and the reserved keys apply in a decoded value, and the fold of the root cast's objects would have kept their deletes, as the parts of one file do. A decoded value would have been one more way to write a patch, and the one way left to give a dict such a key would have been none, on any channel.
- **Only the `.json` casts are data**, a whole-value flag reading the shorthand still. The inconsistency would have moved rather than gone: `--d '{"k-": null}'` deleting while `--sec.json '{"a-": null}'` did not, and a dict field, which has no `.json` cast, receiving no such key from its own flag.
- **Mark a decoded value and let the merge skip it.** `_deep_merge` builds plain dicts as it merges, so the mark would be lost at the first dict-on-dict merge, and the next merge would read the keys.
- **A reserved key in a decoded value is data, as a suffix is.** A pin cannot be: construction reads `{__cast__, __value__}` wherever it stands, and cannot tell where a dict came from, so some reserved keys would have been data and one a value. A data key `__append__` would also be written by `dump_file` as the op.
- **The pin keeps working in a decoded value, the merge's and the file channel's keys being refused.** Principled, as the pin is read by construction like the union tag and `call`, but it kept one exception for a spelling the scalar casts already cover.
