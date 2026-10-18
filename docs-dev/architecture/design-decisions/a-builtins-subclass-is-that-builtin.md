# A builtin's subclass is that builtin

A subclass of `dict`, `list`, `set`, `frozenset`, `tuple`, `str`, `int` or `float` reads as that builtin on every channel and front-end, and is built as the subclass (maintainer's choice, BUG-253).
`_types._builtin_read_as` is the one answer; the shape predicates (`_is_dict`, `_is_list`, `_is_set`, `_is_frozenset`, `_is_tuple`) and the scalar coercions ask it, so construction, the CLI walk, registration, the merge and `dump()` all inherit it.

```python
class Scores(dict[str, int]):
    pass


class Port(int):
    pass


@dataclass
class C:
    od: OrderedDict[str, int] = field(default_factory=OrderedDict)
    counts: Counter[str] = field(default_factory=Counter)
    scores: Scores = field(default_factory=Scores)
    port: Port = Port(80)
```

| Value | Before | Now |
|---|---|---|
| `--od.a 1`, file `od: {a: 1}` | an unknown argument; `Unsupported leaf type collections.OrderedDict[str, int]` | `OrderedDict({'a': 1})` |
| file `counts: {a: 2}` | `Unsupported leaf type collections.Counter[str]` | `Counter({'a': 2})` |
| file `scores: {a: 'x'}` | `Unknown field(s) ['a'] … Valid fields: ['args', 'kwargs']` | `Cannot coerce str 'x' to int at 'scores.a'` |
| `--port 8080` | `Unsupported leaf type <class 'Port'>` | `Port(8080)`, the merged dict holding the plain `8080` |
| `dump(C(...))` | refused, or the subclass handed to the writer | the plain builtins, which read back as the subclasses |

Before, `_is_plain_class` excluded the builtins by module name, not the classes subclassing one, so a subclass was a struct of its constructor's parameters (`args` and `kwargs` for `OrderedDict`), and a parameterized one an unsupported leaf.

The rule has its exceptions where a class reads another way: a dataclass by its fields, a namedtuple by its, an `Enum` (`StrEnum`, `IntEnum`) by its members, and a registered class through its registration ([a registration wins](#a-registration-wins)).
`bool` cannot be subclassed, and a `bytes` subclass stays unsupported, as `bytes` is.

A bare abstract collection is the concrete one, as its parameterized form already was: `collections.abc.Sequence` reads as `list`, `Mapping` as `dict`, `MutableSet` as `set`, where each was a struct with no fields, so `--x 1 2` and a file's list were refused.
PEP 585 made these the spelling to use, `typing.Sequence` and the like being deprecated aliases of them.

## A subclass is typed as a type checker types it

`_types._builtin_args` gives the item types: the subclass's own arguments (`OrderedDict[str, int]`), else the ones its parameterized base declares (`class Scores(dict[str, int])`, followed up the bases), a generic subclass's arguments substituted for its base's TypeVars (`class Registry(dict[str, T], Generic[T])` as `Registry[int]`), and an unbound TypeVar read as `Any`, PEP 484's reading of a missing argument.
`Counter[K]` is `dict[K, int]`, as typeshed declares it: a count is an int, and a file's `2.5` is refused.
Where nothing names the types, as in a bare `OrderedDict`, they are `Any`.

## A subclass is built by its constructor

`_coerce.as_subclass` calls the class with the value built as the builtin, `cls(value)`, a `defaultdict` as `cls(factory, value)`, so the class's own validation runs.
A `ValueError` it raises is a `TypeCoercionError` naming the class and the reason (`Cannot coerce int 70000 to Port at 'port': port out of range: 70000`); a `TypeError`, from a constructor that takes no such value, names the class and `register_leaf_type`, the way to read it otherwise.
A dict subclass whose constructor takes more than the mapping (`def __init__(self, mapping=None, *, strict=False)`) reads as a dict all the same: `strict` is no key a configuration can set, which only a registration changes.
The merged dict holds the builtin a file holds, `8080` and not `Port(8080)`, so a token and a file's value merge alike; `dump()` writes the builtin, which every writer holds and which reads back as the subclass.
It writes any instance of a `str`, `int` or `float` subclass so, read off the value, a `str` or an `Any` field's included: PyYAML's writer refused one with `RepresenterError: cannot represent an object`.

## A defaultdict's factory is its value type's class

A `defaultdict`'s factory is no data, so no channel spells it and no dump writes it: it is derived from the annotation, so that a round trip rebuilds the same object (`_coerce._default_factory`).
It is the class a value is built as: `list` for `list[int]`, `dict` for a mapping, the class itself for a struct, a scalar or a registered leaf.
Where no one class builds a value from nothing (`Any`, a union, a `Literal`, an `Enum`, a type reference, a callable), it is `None`, and the `defaultdict` behaves as a dict.

## A registration wins

A registered subclass is a leaf, read and written through its registration in both directions, as a registered class is never a struct ([a registered leaf is never a struct variant](registered-leaf-is-never-a-struct-variant.md#a-registered-leaf-is-never-a-struct-variant)).
`_builtin_read_as` reads the registry for that reason, and is never cached; `_subclassed_builtin`, which reads none, is what the cached struct test asks.
So `register_leaf_type` accepts a builtin's subclass ([a registration is one construction reaches](a-registration-is-one-construction-reaches.md#a-registration-is-one-construction-reaches)), and it is how a class like the `strict` dict above is read its own way.

## Rejected

- **Only the standard library's subclasses**, pydantic's table (`OrderedDict`, `Counter`, `defaultdict`, `deque`): a user's `dict` subclass would stay a struct of `args` and `kwargs`.
  One rule by class covers both.
- **The collections ABCs' implementers too** (`deque`, `UserDict`, `ChainMap`, a user `Mapping`): their constructors take no one collection (`ChainMap(*maps)`), and none subclasses a builtin; left to [FEAT-53](../../todo/features/FEAT-53-a-collections-abc-implementer-reads-as-a-struct.md).
- **The base winning over a dataclass**: a dataclass subclassing `dict` builds and round-trips by its fields today, as a namedtuple reads by its fields though it subclasses `tuple`.
- **The collection winning over a registration**: registering such a subclass works today, and would then be refused, leaving no way to read a class like the `strict` dict.
- **Bypassing the constructor** (`dict.__new__(cls)` then `update`): it skips the class's validation and leaves unset what its `__init__` sets.
- **The item types from the subclass's arguments alone**, cattrs' reading: `Scores` would be `dict[Any, Any]`, holding the text `'1'` in a `dict[str, int]`, which the built object's annotation says it never holds.
- **A `defaultdict`'s factory from the field's default**: it respects a factory of the user's own, a lambda, but a `defaultdict` in a list or a dict value has no declared default, and would get none.
- **Refusing a `defaultdict` whose value type has no class**, pydantic's choice: a bare `defaultdict` field would stop building.

## Precedents

pydantic validates `OrderedDict`, `Counter`, `defaultdict` (its factory inferred from the value type, refused for `Any`) and `deque` and builds the subclass, but refuses a user's subclass of `dict` or `list`; it dumps them as plain builtins (run).
cattrs builds any `Mapping` subclass by calling it with a dict, reading the item types from its arguments alone (`Scores` holds `'1'`), and refuses a `list` subclass (run).
msgspec refuses all of them (run).
