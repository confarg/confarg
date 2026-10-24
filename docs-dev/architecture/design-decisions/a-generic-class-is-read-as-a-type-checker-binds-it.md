# A generic class is read as a type checker binds it

A parameterized generic class is a struct whose members read with its type parameters bound, the way mypy, pyright and ty bind them (FEAT-13, maintainer-chosen):

```python
@dataclass
class Box[T]:
    item: T


@dataclass
class Tagged[T]:
    item: T


@dataclass
class Labeled[T](Tagged[T]):
    label: str = ""


@dataclass
class Holder:
    b: Box[int]  # --b.item 3 builds Box(item=3), --b.item x is refused
    bare: Box  # T unbound: Any, so --bare.item x builds Box(item='x')
    tagged: Tagged[int]  # class: Labeled builds Labeled[int]: item an int
```

- **A bare generic reads its PEP 696 default, else `Any`**, never its bound: mypy, pyright and ty read `h.bare.item` as `Any`/`Unknown` and a `Defaulted[T = int]`'s as `int`, and none reads a `T: Locator` bound for a bare annotation.
  `_builtin_args` had read an unbound TypeVar as `Any` for a builtin's subclass; it now reads the default too, so one rule binds both.
- **A tag binds through the class's bases**: under `Tagged[int]`, `class: Labeled` builds `Labeled[int]`, as a checker infers `Labeled(item=...)` where a `Tagged[int]` is expected and refuses `Labeled(item="3")`.
  A subclass whose bases fix another argument is refused, so a tag never loosens the field's type.
- **A tag stays a dotted path**: `class: Box[int]` is refused, as it always was.

How the binding is computed: [a generic class reads its parameters bound](../types/introspection.md#a-generic-class-reads-its-parameters-bound) and [a tag binds the class it names through its bases](../types/introspection.md#a-tag-binds-the-class-it-names-through-its-bases).

## Rejected

- **A bound types an unbound parameter** (default, else bound, else `Any`), and a constrained TypeVar its constraints' union.
  More useful to the CLI (`--b.item.<field>` flags, a word refused), but stricter than every type checker on the same annotation.
- **A tag reads its class bare**, with no unification: simpler, but `{class: Labeled, item: x}` would build under `Tagged[int]`, which every checker refuses in Python, so a tag would loosen the declared type.
- **A tag spelling its arguments** (`class: Box[int]`), a type expression read by a restricted AST walk.
  Under a parameterized field the arguments only repeat the declared type or contradict it, so they say something only under `Any`, a bare generic or a same-origin union.
  `dump()` could not always write them back: an instance knows its arguments only when it was built through the alias (`__orig_class__`).
  And one rule would have every reader of a class path take a type expression — tags, `type[X]` values, `call:`, `bind:` and `classfn:` targets — with brackets to quote on the command line.
  Neither Hydra's `_target_` nor jsonargparse's `class_path` takes one (both run: `Error locating target 'genmod.Box[int]'`, and an exit 2).
- **Unwrapping the origin alone**, FEAT-13's first direction: `Box[int]` read as `Box`, its `T` unsupported, then `Any`; the arguments the annotation gives would have been thrown away.

## What it costs

- A union holding one generic parameterized apiece tells its variants apart by the value alone ([limitations](../limitations.md#subclasses)).
- Under `Any` or a bare generic, a tagged generic class reads its defaults, else `Any`.

## Precedents

| Run on 3.12 | `Box[int]` ← `{item: 'x'}` | bare `Box` ← `{item: 'x'}` | `IntBox(Box[int])` ← `{item: 'x'}` |
|---|---|---|---|
| pydantic | refused | `Box(item='x')` | `IntBox(item='x')`: the base's binding is not read |
| cattrs | refused | refused, `Missing type for generic argument T` | refused |
| msgspec | refused | `Box(item='x')` | refused |
| dacite | refused | refused, `should be "T"` | refused |
| confarg | refused | `Box(item='x')` | refused |

confarg reads as msgspec does, which is what the checkers read.
