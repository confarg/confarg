# Int ranks above float

In the [stealing rank](../types/stealing-rule.md#stealing-rule), `int` comes before `float`: a whole number is an `int` and anything else a `float`, in `int | float` and `float | int` alike, from every channel (maintainer's choice, BUG-154).

```python
@dataclass
class C:
    a: int | float = 0
```

| Value | Before | Now |
|---|---|---|
| `--a 1` | `1.0` | `1` |
| `--a 1.5`, `--a 1e3` | `1.5`, `1000.0` | the same: `int` refuses the text |
| `--a 0x10` | `16` | `16` |
| file `a: 1` | `1` | `1` |
| file `a: 1.0` | `1.0` | `1.0` |
| `dump(C(a=1))` | `{'a': 1}` | `{'a': 1}` |

## Why

The order was never argued for: BUG-4 made the rank total and fixed, and read the tutorial's `[float, int, bool, None]` in the order it is written, where the bracket had grouped the numbers ([stealing rule for text in unions](stealing-rule-for-text-in-unions.md#stealing-rule-for-text-in-unions)).
Of the pairs in it, only `int` above `bool` has a reason: `1` is a number and `yes` a bool.
Text goes to the most specific type that accepts it, and `int` is the more specific number; under `float > int`, `int` in `int | float` took only a hex, octal or binary token.

It was BUG-154 that made the order matter for a file: a file's `1` stayed an `int` only because `float` refused it, while `--a 1` built `1.0`.
Once [a float reads an int as its digits](a-float-reads-an-int-as-its-digits.md#a-float-reads-an-int-as-its-digits), the rank alone decides both channels, and `int` first keeps what a file built, matches every precedent for a native value, and lets every number in such a field dump bare.

## Rejected

- **Keeping `float > int`.**
  A file's `1` would become `1.0`, and every `int` such a field holds, its default `0` included, would dump as `{__cast__: int, __value__: 1}`, since a bare `1` reads back as a `float`.
- **An exact type first for a native value**, pydantic's smart mode: a file's `1` the `int`, `--a 1` still `1.0`.
  One text builds two values, which [a union ranks every value](a-union-ranks-every-value.md#rejected) already rejected as two orders for one value.

## Precedents

pydantic (lax and strict) and msgspec keep a native `1` an `int` in `int | float` and `float | int` (run).
For text, pydantic, jsonargparse and tyro follow declaration order, `'1'` being `1` in `int | float` and `1.0` in `float | int` (run); confarg's rank ignores declaration order.
