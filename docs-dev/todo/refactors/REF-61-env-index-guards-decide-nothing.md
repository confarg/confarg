# REF-61 — The index-range guards in the env part matchers decide nothing

**Where:** `src/confarg/_parse_env.py` (`_match_tuple_part`, `_match_namedtuple_part`) ·
**Filed:** 2026-09-26
**Effort:** S · **Risk:** medium · **Impact:** none

Both matchers guard their index lookup with `if 0 <= idx < len(...)`, and no test can tell whether
that guard is there. Each of these survives the whole suite (4197 passed, 1 skipped), verified one
at a time:

- `_match_tuple_part`: `0 <= idx < len(tt)` → `0 <= idx <= len(tt)`, and → `0 < idx < len(tt)`
- `_match_namedtuple_part`: `0 <= idx < len(field_names)` → `0 <= idx <= len(field_names)`
- `_match_tuple_part`: `part.lower()` → `part.upper()` (equivalent for the digit segments the
  index path actually sees; it differs only on the non-numeric fall-through, where the type is
  already `None`)

The reason is that the guard is not what rejects a bad index — `build()` is. Out-of-range env
indices produce their error downstream today, with the guard intact:

```python
class Point(NamedTuple):
    x: int
    y: int

@dataclass
class Cfg:
    pair: Point = Point(0, 0)
    trip: tuple[int, int, int] = (0, 0, 0)

confarg.load(Cfg, argv=[], env={"MYAPP_PAIR__2": "99"}, env_prefix="MYAPP_")
# TypeCoercionError: Cannot construct Point at 'pair': index 2 out of range for 2 fields
confarg.load(Cfg, argv=[], env={"MYAPP_TRIP__3": "99"}, env_prefix="MYAPP_")
# TypeCoercionError: Cannot construct tuple at 'trip': index 3 out of range for length 3
```

So the guard only decides whether a type hint is attached to the segment, and widening or
narrowing it by one changes nothing a caller can see, because `build()` re-derives the same
decision. That is the
[delegate to the canonical function](../../architecture/09-invariants.md#delegate-to-the-canonical-function)
question in miniature: the out-of-range decision has an owner, and the env matchers hold a second
half-hearted copy that neither rejects nor is needed.

Two ways to settle it, and the choice is the work:

- **Drop the guard** and let the index lookup fall through to the `None` type the way a
  non-numeric segment already does, leaving `build()` the sole owner. This is what
  [merge stays unvalidated](../../architecture/09-invariants.md#merge-stays-unvalidated) points
  to. Confirm first that nothing downstream relies on the attached type for an in-range index.
- **Keep it and pin it** with tests at both boundaries — `idx == len(...)` and `idx == 0` — in
  `tests/test_env.py`, which today has no tuple-by-index env test at all
  (`tests/test_namedtuple.py::test_index_segments` covers only in-range 0 and 1).

`_parse_env.py` scores 78% (108 survivors of 495).
