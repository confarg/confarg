# Shared reserved key names live in `_defaults.py`

`__root__` — the key under which a non-struct target's value sits in the merged dict — is written by all three channels and read by `build()`, so the five front-ends must agree on the spelling; every site that spelled it inline was a place they could drift apart.
It is now `_defaults.ROOT_KEY`, next to `LOCALS_KEYS`, which is a reserved name rather than a keyword default too: `_defaults.py` is the home for **any** literal the front-ends have to agree on, not only the public keyword defaults, and its "never repeat the literals" invariant ([invariants](../invariants.md#fragile-couplings)) covers both kinds.

The file-only keys followed once each had a second reader.
`__include__`, `__cast__` and `__value__` were each read in one module, but the CLI, the environment and the mount check now refuse every [reserved key](../config-files/reserved-keys.md#reserved-file-only-keys) through one test (FEAT-3), and `__cast__`/`__value__` were already spelled twice, by the reader in `typedload._construct` and the writer in `_serialize`.
So `_defaults.py` holds `INCLUDE_KEY`, `CAST_KEY`, `VALUE_KEY` and the four list ops' file spellings, and `RESERVED_KEYS` lists them all; `_files.INCLUDE_KEY` is the same object under its owner's name.
The ops' markers stay in `_merge`, which builds them from these spellings ([design decisions](merge-ops-are-markers-no-channel-types.md#merge-ops-are-markers-no-channel-types)).

The rejected alternative was a separate `_reserved.py` collecting the reserved keys.
It names the concept more honestly, but a second module would split the "where do I look this up?" answer in two for no gain: `_defaults.py` already is the module of names the front-ends share.

A key that does have an owner keeps it: `JSON_CAST_NAME` stays in `_cast.py`, the module that decides what a cast means, in the same way that `_parse_cli` owns the reserved-name conflict rules ([invariants](../invariants.md#delegate-to-the-canonical-function)).
`_defaults.py` is for the names with no such home.
