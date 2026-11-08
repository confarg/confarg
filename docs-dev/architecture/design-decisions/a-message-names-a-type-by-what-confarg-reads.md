# A message names a type by what confarg reads

A message names an annotation as confarg reads it, through one function, `_types._spell_type`: its wrappers unwrapped, so an alias, a `NewType` and an `Annotated` are named by the type they stand for; a class by its `__name__`; `None` as `None`; a union by the variants `_union_args` reads, joined by `|`; anything else as Python writes it (`list[int]`, `typing.Literal['a']`).

```python
type IntOrFloat = int | float


@dataclass
class C:
    x: IntOrFloat | bool = 0


confarg.load(C, argv=["--x", "abc"])
# TypeCoercionError: Cannot coerce str 'abc' to int | float | bool at 'x'
```

The spelling is the same on every Python.
Since 3.14 a union is an instance of `typing.Union`, whose `__name__` is `Union`, so the `getattr(tp, "__name__", repr(tp))` each refusal used to spell by hand named every union `Union` there (BUG-277), and a metavar built the same way read `UNION` for `list[int | str]`.
`repr(Optional[int])` reads `typing.Optional[int]` on 3.12 and `int | None` on 3.14; `_spell_type` reads `int | None` on both.
A parameterized generic keeps its arguments: `getattr(list[int], "__name__")` is `list`, which named a `list[int] | bool` union `list | bool`.

A message names what confarg tried, which is what the annotation stands for: a field's own alias is resolved before any message sees it (`_dc_fields`), so `x: IntOrFloat` read `int | float` already, and a variant behind an alias now reads the same way.

**A refusal echoing its caller's argument names it as written.**
`register_leaf_type` and `dump()`'s `native_types` refuse an argument the caller passed, and say what that argument was: `_spell_type(tp, as_written=True)` unwraps nothing, names an alias and a `NewType` by their own name and a union by its variants as written.
`register_leaf_type(UserId, f)` is refused as `register_leaf_type(UserId): UserId is a NewType, which confarg reads as int`, which named by value would read `register_leaf_type(int)`.

**A class is named by `__name__`.**
`Outer.Inner` reads `Inner`, and a class defined in a function reads its own name rather than `test_x.<locals>.C`.
The one exception is `cli/_sources._type_name`, which contrasts two targets one parser cannot both hold and names them by `__qualname__`, since two `Config` classes nested in different holders would otherwise read alike.

**A metavar names a class only.**
It is the class's name upper-cased, or the generic word (`ITEM`, `VALUE`) for anything that is no class, so `list[int | str]` reads `[ITEM ...]` and `list[list[int]]` no longer reads `LIST`.
A registered leaf's parameterized form is named by the class whose registration reads it, `--s PATTERN` for `re.Pattern[str]` as for `re.Pattern` (`cli._build._class_name`).

**A class is never quoted.**
The dump's warning for a value no cast can pin wrote `will not read back as 'Colorish'`; it reads `as Colorish`, as every other message names a class.

## Rejected

- **Naming an alias by its own name**, as pyright and Python's repr do (`IntOrFloat | bool`): a field's own alias is gone before any message, so only a union variant or a root target would keep its name, and the same annotation would be named two ways depending on where it sits.
- **`__qualname__` everywhere**: a class defined in a function, as most of the suite's are, reads `test_x.<locals>.C`.
- **Naming the echoed argument by value too**: a refusal about a `NewType` would say `register_leaf_type(int)`.

## Precedents

mypy names `IntOrFloat | bool` as `int | float | bool`; pydantic names the variants by value (`x.union[int,float].int`); pyright and Python's repr keep the alias (`IntOrFloat | bool`).
