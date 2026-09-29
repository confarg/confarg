# Type introspection

All type knowledge is derived at runtime from ordinary annotations (`_types.py`), because
confarg requires no base class, decorator or field marker
([design decisions](../design-decisions/no-custom-types-required.md#no-custom-types-required)).

- `TypeAliasType` and `Annotated` are unwrapped everywhere (`_resolve_type`).
- Abstract collection types map to concrete ones: `Sequence`/`Iterable`/`Collection` → list,
  `AbstractSet`/`MutableSet` → set, `Mapping`/`MutableMapping` → dict.
- A **struct** is a dataclass or a *plain class* whose `__init__` takes parameters. Builtins,
  `Enum`, `PurePath` and tuple subclasses are never plain classes. `*args` becomes
  `list[T]`, `**kwargs` becomes `dict[str, T]`, both with empty defaults (never required).
- Since Python 3.11 `typing.Any` is a subclassable class and would pass the plain-class
  test; `_is_plain_class` and `_construct_typed` both guard it explicitly.
- `_unwrap_optional` returns Python `None` (not `NoneType`) to mean "multi-variant union";
  callers must handle that sentinel.
