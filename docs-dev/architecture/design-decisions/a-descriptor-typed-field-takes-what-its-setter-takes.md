# A descriptor-typed field takes what its setter takes

A field may accept a wider input than the type it holds — a `Locator` given as a pattern string, a `tuple[int, int]` given as one side — and the spelling for it is a data descriptor, read as type checkers read one (FEAT-40, maintainer-chosen):

```python
class LocatorField:
    def __get__(self, obj, objtype=None) -> Locator: ...
    def __set__(self, obj, value: Locator | str) -> None: ...   # converts a str

@dataclass
class PartSpec:
    locate: LocatorField = LocatorField()

--locate 'foo*'                       # Pattern('foo*'), the descriptor converting
locate: {class: Pattern, pattern: p}  # Pattern('p')
PartSpec(locate='foo*')               # accepted by mypy, pyright and ty: __init__ takes Locator | str
spec.locate                           # Locator to all three
```

confarg types the member by `__set__`'s value parameter and the dumped state by `__get__`'s return, and the conversion stays the descriptor's own, in Python as on every channel.
It needs no marker of confarg's ([no custom types required](no-custom-types-required.md#no-custom-types-required)), and the input type is declared where the type checkers already read it.
How it is read: [a descriptor-typed field takes what its `__set__` takes](../types/introspection.md#a-descriptor-typed-field-takes-what-its-__set__-takes).

- **The annotation alone decides**, installed descriptor or not, as pyright and ty read `locate: LocatorField` converted in `__post_init__` (mypy refuses `A(locate="x")` there).
- **The dump writes what `__get__` gives**: the object dump records state ([the object dump is forensic](the-object-dump-writes-state.md#the-object-dump-is-forensic)), so a held value the input does not take dumps and does not read back, as an `init=False` field does.
- **A descriptor returning itself on class access is no default**: the field is required, the refusal naming the descriptor ([types](../types/introspection.md#a-descriptor-returning-itself-on-class-access-is-no-default)).

## Rejected

- **FEAT-40's `Accepts` marker**, `Annotated[Locator, Accepts(str, Pattern)]`, and its `__post_init__` variant, the annotation saying what the field holds and a marker what it takes.
  The marker is a custom annotation, and it widens confarg's channels only: every checker refuses `PartSpec(locate="foo*")` in Python, where the descriptor's `__init__` takes it.
- **A widened annotation normalized in `__post_init__`** (`locate: Locator | str`) is no design: it works today, and costs every consumer an `isinstance` to narrow `spec.locate`, the reason the feature exists.
- **Only an installed descriptor**, detected by the class attribute: it matches mypy and what runs, but the annotation-only form converted in `__post_init__` would stay refused, and detection would read a runtime attribute where every other type question reads the annotation.
- **Dumping against `__set__`'s type**: every dump that succeeds would read back, but a handle-only descriptor's state could not be recorded at all.
- **A self-returning descriptor as the default Python takes**: the instance would hold the descriptor, and the failure would surface at `dump()` or at the attribute's first use.
  **Refusing the class outright** would block a configuration that always sets the field.

## Precedents

None of the libraries confarg is measured against reads a descriptor-typed field (all run on `locate: LocatorField`, installed or not, given `'foo*'`): pydantic cannot generate a schema for `LocatorField`, cattrs finds no structure hook, msgspec and dacite expect a `LocatorField`, tyro calls the annotation unsupported, jsonargparse expects a path or an import path, and OmegaConf refuses the annotation.
The type checkers are the precedent: mypy, pyright and ty type the installed form's `__init__` parameter by `__set__` and the attribute by `__get__`, and PEP 681 dropped its own opt-in for descriptor-typed fields once it found dataclasses already support them.
The typing spec's `converter=` on `dataclass_transform` field specifiers, and attrs' `field(converter=)`, put the conversion in a function the checkers read the input type off; the stdlib's own PEP 712 converter was rejected in 2024.
