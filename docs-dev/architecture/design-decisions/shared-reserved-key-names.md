# Shared reserved key names live in `_defaults.py`

`__root__` — the key under which a non-struct target's value sits in the merged dict — is
written by all three channels and read by `build()`, so the five front-ends must agree on
the spelling; every site that spelled it inline was a place they could drift apart.
It is now `_defaults.ROOT_KEY`, next to
`LOCALS_KEYS`, which is a reserved name rather than a keyword default too: `_defaults.py` is
the home for **any** literal the front-ends have to agree on, not only the public keyword
defaults, and its "never repeat the literals" invariant
([invariants](../invariants.md#fragile-couplings)) covers both kinds.

The rejected alternative was a separate `_reserved.py` collecting `__root__` alongside
`__include__`, `__cast__` and `__value__`. It names the concept more honestly, but those
three are file-only keys read in one module each
([config files](../config-files/reserved-keys.md#reserved-file-only-keys)) — they have an owner, and a literal with
an owner is not the problem this invariant exists to prevent. A second module would split the
"where do I look this up?" answer in two for no gain.

A key that does have an owner keeps it: `JSON_CAST_NAME` stays in `_cast.py`, the module that
decides what a cast means, in the same way that `_parse_cli` owns the reserved-name conflict
rules ([invariants](../invariants.md#delegate-to-the-canonical-function)). `_defaults.py` is for the
names with no such home.
