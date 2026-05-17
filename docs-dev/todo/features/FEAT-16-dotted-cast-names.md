# FEAT-16 — Let `__cast__` name a leaf type by dotted path

**Where:** `src/confarg/typedload/_construct.py` (`_try_pinned_dict`), `src/confarg/_cast.py`
**Effort:** M · **Risk:** medium · **Impact:** behavior

`__cast__` accepts a scalar cast name or a registered leaf's `__name__`, so it cannot name an
unregistered `Enum`. That is the one variant kind `dump()` cannot pin when a sibling steals its
scalar back — `str | LogLevel` holding a member dumps `"debug"` and rebuilds as a `str`, and
`dump()` can only warn ([10-design-decisions.md#a-stolen-leaf-dumps-with-its-cast](../../architecture/10-design-decisions.md#a-stolen-leaf-dumps-with-its-cast)).
Accepting `{__cast__: "mymod.LogLevel"}` would close it: `_coerce_leaf` already builds any
`Enum`, and a dotted path in a file is what the `class` tag and a callable `fn:` already are.

What the design pass has to settle:

- **Only a leaf may be named.** An unrestricted dotted cast becomes a second, weaker spelling of
  the class tag, against [an explicit tag opts a leaf back in](../../architecture/10-design-decisions.md#an-explicit-tag-opts-a-leaf-back-in).
  Restrict it to what `_coerce_leaf` accepts — `Enum` and registered leaves — and point the
  error at `class:` otherwise.
- **Typo detection.** Keep the closed-list "Unknown `__cast__` type" message for a bare name;
  only a dotted name is an import.
- **Idempotence.** `cast_name_for_type` returns `tp.__name__`, so a file saying `mymod.Color`
  would re-dump as `Color` and stop reading back. It must emit the dotted form for a type that
  is neither a scalar cast nor registered.
- **Parity.** `--value.mymod.Color debug` is not expressible: dotted suffixes collide with
  nested paths and with `detect_force_cast`'s closed suffix set. This widens the approved
  file-only divergence ([09-invariants.md#cross-channel-parity](../../architecture/09-invariants.md#cross-channel-parity))
  and needs the maintainer's explicit approval as such.
- **Scope.** It does not remove the warning: a `Literal` over `Enum` members has no dotted name,
  and a collection variant is not a leaf coercion target at all.
