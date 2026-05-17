# REF-51 — Hot error messages and the dotted-name format live outside their owners

**Where:** `src/confarg/exceptions.py`, `src/confarg/_parse_cli.py`, `src/confarg/_files.py`,
`src/confarg/_serialize.py`, `src/confarg/typedload/_construct.py` · **Filed:** 2026-09-24
**Effort:** M · **Risk:** low · **Impact:** none

`exceptions.py` has no near-identical classes worth collapsing — the marker classes are public API
and two to four lines each — and it already carries the right convention in
`InvalidConfigFileError` and `LocalsError`, whose messages are classmethod factories. The waste is
that the hottest messages never got that treatment and stayed as f-strings at the call sites:

- "Unknown argument: … (field '…' not found)" in four places in `_parse_cli.py`, three of them
  byte-identical;
- the `__include__`-with-siblings message, verbatim twice in `_files.py`;
- the structured-target message from
  [REF-44](REF-44-cli-root-json-fold-duplicates-the-env-one.md), verbatim in three channels;
- the `config_flag` hint, built twice inside `exceptions.py` itself.

The second half is the one with a bug attached. The dotted name of a type —
`f"{tp.__module__}.{tp.__name__}"` or `f"{tp.__module__}.{tp.__qualname__}"` — is spelled at
**twelve sites in two different spellings** across `_serialize.py`, `_construct.py`,
`_callable.py` and `_coerce.py`. That is exactly how
[BUG-41](../bugs/BUG-41-nested-class-tag-dumps-name-not-qualname.md) happened: the writer picked
`__name__`, the reader `__qualname__`, and a nested class stopped round-tripping. One
`_dotted_name()` with one owner is the durable fix, so sequence this ticket with that bug rather
than patching the two serialization sites.

Fold in while there: the four `type(data).__name__` sites of
[BUG-40](../bugs/BUG-40-strtoken-leaks-into-error-messages.md), which should all go through
`_coerce._src_type` so `_StrToken` cannot reach a message
([09-invariants.md#tokens-mean-untyped-text](../../architecture/09-invariants.md#tokens-mean-untyped-text)).
