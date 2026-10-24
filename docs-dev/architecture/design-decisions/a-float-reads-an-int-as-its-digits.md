# A float reads an int as its digits

A `float` leaf takes a file's `int`, a native one from `from_dict()` and an expression's integer result, and reads it as its digits read on the CLI: `timeout: 1` is the `1.0` that `--timeout 1` is (BUG-154).
A `bool` is still refused, though `bool` subclasses `int`, and the tower runs one way: a file's `1.0` is no `int`, as `--port 1.0` is none.

```python
@dataclass
class Config:
    timeout: float = 0.5
    t: tuple[float, float] = (0, 0)
```

Until BUG-154, `_coerce_float_value` passed a native `float` and parsed a token, and refused the native `int` every file format writes for a whole number, so a file had to write `1.0` where the CLI took `1`.
The same refusal met a class's own default once a source patched it: `--t.1 2.5` builds the default `(0, 0)` through construction, and failed on its first `0`.
An untouched default is never built ([a field default is the base layer](a-field-default-is-the-base-layer.md#untouched-defaults-are-taken-out-again)), so `Config()` and `load(Config)` both keep the `(0, 0)` the class wrote.

An expression reads the value construction builds ([a reference reads the built value](an-expression-reads-a-typed-leaf-as-its-object.md#how-each-stage-carries-it)), so a file's `timeout: 1` reads `1.0` in `${str(timeout)}`, as the token does.

Precision is not checked: `9007199254740993` reads as `9007199254740992.0`, as the same digits do on the CLI, and as every precedent below reads it.

## A number too large for a float reads as infinity

`float(10**400)` raises `OverflowError` where `float("1" + "0" * 400)` is `inf`, so the two spellings of one number would part.
The digits win: a file's integer too large for a float is the infinity of its sign, as the token of its digits is, and as a file's `1e400` already is once its parser has read it (maintainer's choice).

It warns, with `FloatOverflowWarning`, a subclass of `ConfargWarning` that a filter on either category cancels (maintainer's choice).
The warning names where the number was written:

- a file's value, and a union's token, which construction coerces, by the field's path: `… is too large for a float and reads as inf at 'timeout'`;
- a CLI or environment token, which `_try_coerce` coerces while parsing, by the flag or the variable the user typed, since a parser reads it before the field's path is spelled: `1e400 for --timeout is too large for a float and reads as inf`.

The token reads as its infinity while parsing, as before, so `merge()` holds `inf` and its dump reads back; an earlier draft left the token as text for construction to warn with the path, and `merge()`'s dump then wrote `'1e400'`, which no file reads back as a float.
Only the conversions confarg makes warn.
An infinity word (`inf`, `-Infinity`) is meant and never warns; a file's float literal that overflows is `inf` before confarg sees it, as a deliberate `.inf` or `Infinity` is, and passes silently ([FEAT-52](../../todo/features/FEAT-52-a-file-float-literal-that-overflows-reads-as-inf-silently.md)); neither does an expression's float arithmetic (`${1e308 * 10}`).
Each overflow warns once: the adapters' registration runs vanilla's loop over argv to type the flags it spells, and that dry run is silenced, as it is suppressed for errors.
An expression reading the value warns of nothing either: construction warns of what it builds.

## Rejected

- **Refusing a file's overflowing integer.**
  pydantic refuses the Python int `10**400` and msgspec every overflow, but the CLI reads the same digits as `inf`, so one text would build in one channel and fail in another.
- **Refusing every finite overflow**, `--f 1e400` included, and keeping `inf` for an infinity word.
  It cannot be complete: a file's `1e400` is `inf` when its parser hands it over, indistinguishable from `.inf`.
- **Warning only for a file's integer.**
  The same digits would warn in a file and not on the command line.
- **The plain `ConfargWarning`**, which only a message regex cancels alone, and **a `load()` option**, a parameter every entry point of five front-ends would carry for a rare case.

## Precedents

| | `float` field, file `1` | file `10**400` | text `1` followed by 400 zeros |
|---|---|---|---|
| pydantic 2.14 (run) | `1.0` | refused | `inf` |
| msgspec 0.22 (run) | `1.0` | refused | refused, from JSON |
| cattrs (run) | `1.0` | refused | — |

pandas and pydantic give each kind of warning its own subclass to filter by category (`PerformanceWarning`, `PydanticDeprecatedSince20`); numpy warns with `RuntimeWarning` and scopes it with `np.errstate`.
