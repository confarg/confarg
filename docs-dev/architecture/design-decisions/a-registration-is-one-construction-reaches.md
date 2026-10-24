# A registration is one construction reaches

`register_leaf_type` accepts a class construction asks the registry for, and refuses every other key with a `TypeError` (maintainer's choice, BUG-222).
The one answer is `typedload._coerce._registration_refusal`.

| Key | Why no value would ever reach it |
|---|---|
| a `NewType` | it reads as its supertype ([a NewType is its supertype](#a-newtype-is-its-supertype)) |
| `tuple[int, int]`, `int \| str`, `Annotated[int, …]`, `Literal['a']`, a `TypeAliasType` | no class: shape dispatch, the union walk or a wrapper claims the type, never the registry |
| `int`, `str`, `bool`, `float`, `None`, `Any`, `type`, an `Enum` | a built-in leaf or a type reference confarg reads itself, before it asks the registry |
| `list`, `dict`, `tuple`, `set`, `frozenset`, a namedtuple, `Callable` | a shape `_type_kind` names before a leaf |
| `object` | every value is an instance of it, so the registration would pass every value through as its own |

```python
UserId = NewType("UserId", int)

confarg.register_leaf_type(UserId, f)
# TypeError: register_leaf_type(__main__.UserId): UserId is a NewType, which confarg reads as int;
#            register a class confarg does not read itself
```

Before, every such key was accepted and then ignored without a word: shape dispatch claimed a generic alias, the scalar coercions an `int`, the Enum coercion an `Enum`.
A `NewType` crashed every value with Python's own `TypeError` from an `isinstance` until FEAT-51 looked a value's class up instead, after which it built by accident.
A refusal at registration names the mistake where it is made, rather than at the first value that silently reads some other way.

A class confarg reads nothing as, such as `complex`, a plain class, or a built-in leaf registered again (`Path`, `Decimal`, a date type), is accepted as before, and so is a builtin's subclass, which a registration takes out of the builtin's reading ([a registration wins](a-builtins-subclass-is-that-builtin.md#a-registration-wins)).
The refusal is a `TypeError`, not a `ConfargError`: a key no value reaches is a programming mistake, not a configuration one, and an `except ConfargError` meant for bad input should not catch it.
`dump()`'s `native_types` check refuses a type that is no registered leaf the same way.

## A NewType is its supertype

`_resolve_type` unwraps a `NewType` to its supertype, as it unwraps `Final` ([wrappers are transparent](../types/introspection.md#wrappers-are-transparent)): a `UserId` field reads, merges, registers its flags and dumps as an `int` on every channel and front-end, a `NewType` over `list[str]` as that list, and one over a dataclass as that struct.
At runtime a `NewType`'s value is its supertype's, `UserId(3)` the int `3`, so nothing tells a dump which `NewType` a value came from.
That is why a `NewType` cannot be registered: a coercion keyed on it could run on the way in, but the serializer, which `dump()` looks up by the value's class, never on the way out.

Before, a `NewType` field was an unsupported leaf on every channel, and `dump()` told the user to register it.

## Rejected

- **Refusing only a key that is no class**, the ticket's first reading: `int`, an `Enum` or a namedtuple stay accepted and ignored, the same silent mistake.
- **Letting the registry win over every shape**, so that `int` or an `Enum` reads through a registered coercion: the parsers' eager coercion of a number token, the stealing rank and union disambiguation all rely on the scalars being fixed.
- **Keying a registration on a `NewType`**, as cattrs allows: its unstructure hook runs only when the caller passes `unstructure_as=`, the value alone being the supertype's (run), and confarg's dump would meet the same wall under `Any` or in a union.
- **A `ConfargError`**: every other error confarg raises is one, but this one is not about a configuration.

## Precedents

pydantic, msgspec and cattrs all read a `NewType` as its supertype (`"7"` builds `7` for `NewType("UserId", int)`), and msgspec's `dec_hook` is called with the supertype, never the `NewType` (run).
`functools.singledispatch`'s `register` refuses `tuple[int, int]` with a `TypeError` naming it as no class or union type.
