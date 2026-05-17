# FEAT-13 — Struct types that are generic

**Where:** `src/confarg/_types.py` (`_resolve_type`, `_is_plain_class`) · **Filed:** 2026-09-13
**Effort:** L · **Risk:** high · **Impact:** behavior

A field annotated with a parameterized user generic is rejected outright: `item: GBase[Any]`, where
`GBase[T]` is an ABC with dataclass subclasses, gives `TypeCoercionError: Unsupported leaf type
GBase[typing.Any] at 'item'`. `_resolve_type` unwraps `TypeAliasType` and `Annotated` but not a
generic parameterization, so `_is_dc` and `_is_plain_class` both fail their `isinstance(tp, type)`
test, nothing else claims the type, and `_coerce_leaf` falls through to its "unsupported" arm. Tag
resolution would fail next anyway — `issubclass(cls, GBase[Any])` raises `TypeError`. The
workaround, never parameterizing a tag base, costs the user the type argument everywhere, because
the bare form then trips a type checker's missing-type-argument rule.

Fix direction: unwrap `get_origin()` for *user* generics before struct detection and before the
subclass test. It cannot go into `_resolve_type` unconditionally — `_is_list`, `_is_dict` and
`_is_union` read `get_origin` themselves, so the ordering is the design question, and
`_resolve_type` sits under every channel
([09-invariants.md#fragile-couplings](../../architecture/09-invariants.md#fragile-couplings)).
See [05-types-and-construction.md#type-introspection](../../architecture/05-types-and-construction.md#type-introspection)
and [#inheritance](../../architecture/05-types-and-construction.md#inheritance).
