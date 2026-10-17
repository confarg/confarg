# Decimal and UUID are built-in leaves

`Decimal` and `UUID` are registered leaves with no call to `register_leaf_type`, as `Path` is: `_coerce._LEAF_COERCIONS` holds `_coerce_decimal` and `_coerce_uuid`, and `_LEAF_SERIALIZERS` writes both as their `str()` (maintainer-chosen).

Unregistered, each was a struct of its constructor's parameters ([a struct's members are its constructor's parameters](a-structs-members-are-its-constructors-parameters.md#which-signature-is-read)), and neither outcome was one the design wanted:

```python
@dataclass
class C:
    price: Decimal = Decimal("1.5")
    id: UUID = UUID(int=1)
```

- `Decimal` was a struct of `value` and `context`: `--price 1.1` was refused (`expected dict, got str '1.1'`) where `--price.value 1.1` built it, and `dump()` refused the field, since a `Decimal` holds no `value`.
- `UUID` was a struct of seven alternative parameters, each of which it exposes as an attribute: `dump()` wrote all seven, `{'hex': …, 'bytes': …, 'int': 1, …}`, and reading that back raised `UUID`'s own `TypeError` (`one of the hex, bytes, bytes_le, fields, or int arguments must be given`).

A type whose text is its value is a leaf, and these are the standard library's commonest beside `Path`.
Registered, each is everything a registration makes a type: it outranks every other leaf kind in a union, so `int | Decimal` reads `5` as `Decimal('5')` ([stealing rule](stealing-rule-for-text-in-unions.md#stealing-rule-for-text-in-unions)); an expression computes with the object ([an expression reads a typed leaf as its object](an-expression-reads-a-typed-leaf-as-its-object.md#an-expression-reads-a-typed-leaf-as-its-object)); a default is laid as the base layer; `Decimal` and `UUID` are `__cast__` names; and an explicit class tag still builds either from its fields ([an explicit tag opts a leaf back in](an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in)).
Registering either again replaces the built-in reading, as it does for `Path`.

## A file's float reads as it is written

YAML, JSON and TOML parse `price: 1.1` as a float before confarg sees it, and `Decimal(1.1)` is that float's binary expansion, `Decimal('1.100000000000000088817841970012523233890533447265625')`, where argv's `--price 1.1` is `Decimal('1.1')`.
`_coerce_decimal` reads a float through its `repr`, the shortest text that reads back as the same float, so every channel's `1.1` is one decimal.
Digits a float cannot hold are lost when the parser reads the file, before any coercion runs; a file that needs them writes the number quoted.

`dump()` writes a decimal as its `str()`, a string, so a file holds `'1.1'` and reads it back with every digit and the exponent kept (`1.10`, `1E+2`, `-0`, `NaN`).
Written as a number, it would read back through a float.

## What each refuses

`_coerce_decimal` refuses a `bool`, as the `int` and `float` coercions do ([leaf coercion](../types/leaf-coercion.md#leaf-coercion)), where `Decimal(True)` is `Decimal('1')`.
It turns a malformed text's `decimal.InvalidOperation`, an `ArithmeticError`, into the `ValueError` construction reports as a `TypeCoercionError`.
`_coerce_uuid` takes text only, where `UUID(5)` raises an `AttributeError`.
Under the registration the docs used to recommend, `register_leaf_type(Decimal, Decimal)` and `register_leaf_type(UUID, UUID)`, `--price abc` and a file's `id: 5` both escaped `build()` as those raw exceptions.

## Rejected

- `Decimal` itself as the coercion: it reads a float exactly, which is what made a file's `1.1` differ from argv's.
- Making a class like `Decimal`, whose constructor parameters it does not hold, an unsupported leaf rather than a struct: a rule about every plain class, which still leaves both types unusable until registered.

## Precedents

| | `Decimal` built in | a file's `1.1` reads as | a decimal dumps as | `UUID` built in |
|---|---|---|---|---|
| jsonargparse 4.52 (run) | as any class built from text | `Decimal('1.1000…25')` | `1.1`, a number, which reads back as the expansion | yes, dumped as its text |
| pydantic v2 *(from its documentation, not run)* | yes | `Decimal('1.1')`: a value is converted to `str` first | a string, in JSON mode | yes, a string |
| msgspec *(from its documentation, not run)* | yes | `Decimal('1.1')`: a JSON number is read from its text | a string by default (`decimal_format`) | yes, a string |
| omegaconf | no | — | — | no |

confarg sides with pydantic and msgspec on both directions; jsonargparse shows the cost of the alternative on each.
