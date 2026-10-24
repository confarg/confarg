# A Literal member is what PEP 586 allows

PEP 586 allows a `Literal` member to be an `int`, `str`, `bytes`, `bool`, an `Enum` member or `None`, and nothing else; `typing` does not check it at runtime, so confarg does (maintainer's choice, BUG-255).
confarg reads the members a value can spell: an `int`, `str`, `bool`, `Enum` member or `None` (`_types._literal_values`).
The other two kinds are told apart, because they are two different mistakes:

- **A `bytes` member is valid typing confarg cannot read**, as it reads no `bytes` field.
  It is skipped, as an unsupported branch of a union is: PEP 586 reads `Literal[b"ab", "cd"]` as `Literal[b"ab"] | Literal["cd"]`.
- **Any other member makes the annotation invalid**, which every type checker already reports.
  It is refused wherever a value reaches it ([a forbidden member makes the annotation invalid](#a-forbidden-member-makes-the-annotation-invalid)).

```python
@dataclass
class C:
    a: Literal[b"ab", "cd"] = "cd"
    b: Literal[b"ab"] = b"ab"
    c: Literal[1.0, 2.5] = 2.5  # rejected by ty, mypy and pyright
    d: Literal[1.0] | str = ""  # rejected by ty, mypy and pyright
```

| Value | Before | Now |
|---|---|---|
| `--a cd` | `'cd'` | `'cd'` |
| `--a "b'ab'"`, file `a: !!binary YWI=` | `b'ab'`, matched by `str()` or natively | `Cannot coerce … to Literal['cd'] at 'a'` |
| `dump(C(a=b"ab"))` | `b'ab'`, which a JSON or TOML writer refuses | refused, naming the bytes member |
| `--b ab` | `Cannot coerce str 'ab' to Literal(b'ab',)` | `Unsupported leaf type typing.Literal[b'ab'] at 'b'` |
| `--c 1`, file `c: 1.0` | `1.0`, through `float`'s coercer | `Invalid annotation Literal[1.0, 2.5] at 'c': its member 1.0 is a float; …` |
| no value for `c` | `2.5` | `2.5`: the refusal is lazy |
| `--d 1` | `1.0` | the same refusal; `str` does not take the value instead |
| `--d a` | `'a'` | the same refusal |

The refusal is lazy, as an unsupported leaf's is: a field no value reaches keeps its default, and `dump()` refuses to write a value typed by it.
Registration offers the members confarg reads as the flag's choices, and none for a `Literal` construction refuses, so the framework hands the value to confarg rather than refusing it with members no value reads as.

## A forbidden member makes the annotation invalid

`_types._forbidden_literal_member` is the one answer: the first member PEP 586 forbids that a type reaches, through a union's branches and a collection's item types, never into a struct, whose fields are reached as fields.
`_coerce._refuse_a_forbidden_literal` raises it as a `TypeCoercionError`, asked by `_coerce_leaf` for a leaf, by `construct()` for a union before any branch is tried and before a `None` is taken, and by the serializer for a leaf and a union.

The union is refused, not walked, because a union skips a branch that refuses the value: an unsupported `bytes` branch is skipped so that `bytes | int` still reads an int ([an unsupported branch is skipped, and named](#an-unsupported-branch-is-skipped-and-named)).
Had the invalid `Literal` been one more unsupported leaf, `d` above would have built the text `'1'` where it built `1.0`, without a word.
A valid annotation's unsupported branch has a use, a value set by code that builds the object; an invalid annotation has none, since no checked program holds one.

## An unsupported branch is skipped, and named

A branch of a union that construction reads no value as, such as `bytes`, `complex` or a class nobody registered, is skipped, as it was: `bytes | int` reads `--x 1` as `1`, its `bytes` branch left to code that builds the object.
A value no branch takes is refused naming the branches skipped so (`_construct._reads_nothing`): `Cannot coerce str 'ab' to bytes | int at 'x'; bytes is no leaf type confarg reads`.
Before, the refusal read as a wrong value, though no value could have reached `bytes`.

## Rejected

- **PEP 586's members exactly**, a `bytes` member read.
  No channel spells one but YAML's `!!binary`, a token matched only the member's `str()` (`--a "b'ab'"`), and the JSON and TOML writers refuse the dumped value; a `bytes` field is no leaf either.
- **Making `bytes` a leaf** for the member's sake.
  It needs a spelling per channel and per writer, base64 or otherwise, which a `bytes` field would need first.
- **Refusing eagerly**, as msgspec does when it builds a decoder: every `load()`, `build()` and `populate_*` would walk the whole target type first, a walk confarg has nowhere else, and an untouched `bytes` field would still be refused lazily.
- **Refusing a union with any unsupported branch.**
  Stricter and simpler, but `bytes | int` would stop reading an int, though the annotation is valid and the int branch takes the value.
- **Skipping a forbidden `Literal` branch like a `bytes` one.**
  One rule, but it changes `d`'s value without a word, the type checker's warning on the annotation being the user's only clue.

## Precedents

msgspec refuses every `Literal` member but `None`, a bool, an int and a str, `Enum` members and `bytes` included, when it builds a decoder, whether or not the data holds the field (run).
pydantic and cattrs accept any member and match it by equality, so `Literal[1.0]` takes `1` (run).
For a union with a branch they cannot read (`Foo | int`, `Foo` a class none of them knows), pydantic, msgspec and cattrs all refuse the whole type; none skips the branch (run).
