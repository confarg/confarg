# A message names a type by what confarg reads

A message names an annotation as confarg reads it, through one function, `_types._spell_type`: its wrappers unwrapped, so an alias, a `NewType` and an `Annotated` are named by the type they stand for; a class by its `__name__`; `None` as `None`; a union by the variants `_union_args` reads, joined by `|`; a `Literal` by the members `_literal_values` reads (`Literal['a']`); a generic by its origin's name and its arguments spelled the same way (`list[int | None]`, `dict[str, Any]`); anything else as Python writes it.

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

**A type reads alike alone and nested.**
A generic's arguments go through `_spell_type` too, a Callable's parameter list and `...` included, so `Any` reads `Any` inside `dict[str, Any]` as it does alone, and `list[Optional[int]]` reads `list[int | None]` on every Python, where its `repr` reads `list[typing.Optional[int]]` on 3.12.
Writing the arguments by `repr`, as REF-97 did, left the version dependence it removed from a union at the top level.
A registered leaf's parameterized form follows: `re.Pattern[str]` reads `Pattern[str]`, its class by `__name__`.

**A `Literal` reads the members confarg reads.**
`Literal['a', b'x']` reads `Literal['a']`, alone and as a union's variant, since no value reads as the `bytes` member ([a Literal member is what PEP 586 allows](a-literal-member-is-what-pep-586-allows.md#a-literal-member-is-what-pep-586-allows)); one confarg reads no member of, `Literal[b'ab']`, is named by what it holds.
A lone `Literal` refused a value through a spelling of its own, `Literal['a', 'b']`, while a union holding it read `typing.Literal['a', 'b']`; both read `Literal['a', 'b']` now.
Echoed as written, it names every member, which the refusal of a member PEP 586 forbids quotes (`Literal[1.0, 2.5]`).

**A message that cannot call it is handed the text.**
`exceptions.py` imports nothing from confarg ([invariants](../invariants.md#fragile-couplings)), so `MissingFieldError` takes its field's type already spelled: `of type int`, where it wrote its `repr`, `<class 'int'>`, and `typing.Optional[int]` on 3.12.

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
