# REF-70 — `_dataclass_subclasses` is named for dataclasses but returns plain-class structs

**Where:** `src/confarg/_types.py` (`_dataclass_subclasses`) · **Filed:** 2026-09-29
**Effort:** M · **Risk:** low · **Impact:** none

The docstring says "all struct subclasses", and that is what the walk returns: a plain class
that `_is_struct` accepts shows up alongside the dataclasses, so the name undersells the
traversal. Observed while fixing
[BUG-44](../../architecture/05-types-and-construction.md#inheritance): the probe returned a
plain non-`@dataclass` `Mixin` subclass in the result. Rename to `_struct_subclasses` and
update the two callers (`confarg/cli/_build.py`, `confarg/_parse_cli.py`). Private symbol, so
nothing public moves.
