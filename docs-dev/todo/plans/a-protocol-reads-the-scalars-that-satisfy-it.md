# Plan — A Protocol reads the scalars that satisfy it

**Drafted:** 2026-10-28 · **Status:** approved · **Tickets:** [FEAT-59](../features/FEAT-59-a-protocol-scalars-satisfy-reads-as-their-union.md), [BUG-299](../bugs/BUG-299-a-union-with-a-struct-variant-registers-no-cast-flag.md) · **Builds on:** [the Protocol plan](protocol-typed-fields.md)

Under FEAT-57 a Protocol field takes its value through the `class:` tag only ([a Protocol takes no plain value, for now](protocol-typed-fields.md#a-protocol-takes-no-plain-value-for-now)), so a field typed by a Protocol that a plain value satisfies cannot be given one:

```python
from typing import SupportsFloat


@dataclass
class C:
    ratio: SupportsFloat = 1.0
```

`--ratio 3.5`, a file's `ratio: 3.5` and `from_dict(C, {"ratio": 3.5})` are refused, asking for `--ratio.class`, and `dump(C())` writes `ratio: 1.0` with the warning that it will not read back, so a file dumped from the defaults does not load.

The design was settled in one grilling session; each decision below names what it rejected and what the precedents do.
The examples use these Protocols beside the standard library's `SupportsFloat`, `SupportsInt` and `SupportsIndex`:

```python
class Printable(Protocol):
    def __str__(self) -> str: ...  # object provides it: every scalar conforms


class Empty(Protocol):  # no members: every class conforms (the Protocol plan)
    pass


class HasUpper(Protocol):
    def upper(self) -> str: ...


class SupportsLen(Protocol):  # an author thinking of collections
    def __len__(self) -> int: ...


class HasName(Protocol):
    name: str
```

## Decisions taken

### A Protocol reads a plain value through the scalars that satisfy it

A Protocol that one of the five scalar types satisfies — `bool`, `int`, `float`, `str`, `None`, the scalar types — reads as the union of those scalars and of its implementers, which the tag still names: `ratio: SupportsFloat` reads as `int | float | bool` beside `--ratio.class`.
A scalar satisfies it by FEAT-57's rule, its members and its methods' call shapes ([a class conforms by its members and its methods' call shapes](protocol-typed-fields.md#a-class-conforms-by-its-members-and-its-methods-call-shapes)), every member looked up in the scalar's `__mro__`, as an instance sees it: no scalar instance has an attribute of its own, so the class answers for the instance, data members included, before any value is read.
A Protocol no scalar satisfies (`HasName`, `SupportsBytes`, `Greeter`) reads as FEAT-57 says, `class:` only.

| Protocol | its scalars | `--x 3.5` | `--x 3` | `--x yes` | `--x none` | `--x abc` |
|---|---|---|---|---|---|---|
| `SupportsFloat`, `SupportsInt` | bool, int, float | `3.5` | `3` | `True` | refused | refused |
| `SupportsIndex` | bool, int | refused | `3` | `True` | refused | refused |
| `HasUpper`, `SupportsLen` | str | `'3.5'` | `'3'` | `'yes'` | `'none'` | `'abc'` |
| `Printable`, `Empty` | bool, int, float, str, None | `3.5` | `3` | `True` | `None` | `'abc'` |
| `HasName` | none | `class:` only | | | | |

Each row reads exactly as the explicit union of its scalars reads today (run), on every channel: a token is converted, a file's value only recognized ([a union ranks every value](../../architecture/design-decisions/a-union-ranks-every-value.md#a-union-ranks-every-value)), so a file's `x: yes` under `Printable` stays `'yes'`.

Rejected: **refusing it and recording the refusal**, a Protocol taking `class:` only for good: no precedent converts text into a Protocol, but a field whose default is a plain value would keep dumping a file that does not load.
**Passing a file's native value through when its type conforms, never converting text**, msgspec's rule and pydantic's under `arbitrary_types_allowed`: a file's `3.5` would load while `--ratio 3.5` needed `--ratio.float 3.5`, two readings of one value by channel, which [a union ranks every value](../../architecture/design-decisions/a-union-ranks-every-value.md#rejected) rejected.

Precedents (run): pydantic 2.14 refuses `SupportsFloat` at schema build, and under `arbitrary_types_allowed` only runs `isinstance`, so `3.5` passes and `'3.5'` is refused; msgspec 0.22 passes `3.5` by the same `isinstance` and refuses `"3.5"`, and `3.5` under `SupportsIndex`; cattrs 26.2 (`Unsupported type`), tyro 1.0 (`Unsupported type annotation`) and jsonargparse 4.53 refuse the type.

### The candidates are the scalars, never a registered leaf

The candidate set is fixed: the five scalars, never `Path`, `Decimal`, `UUID`, the date and time types or a type a user registers.

| Protocol | the scalars and the whole registry | the scalars and confarg's own registrations | chosen: the scalars |
|---|---|---|---|
| `SupportsFloat` | bool, int, float, Decimal, and a registered `Fraction` | bool, int, float, Decimal | bool, int, float |
| `SupportsInt` | and `UUID` (`UUID.__int__`) | bool, int, float, Decimal, UUID | bool, int, float |
| `HasName`, a `__fspath__` Protocol | Path | Path | none: `class:` only |

Rejected: **the whole registry**, the ticket's first idea.
The registry is process-global and a registered leaf ranks first ([stealing rule](../../architecture/types/stealing-rule.md#stealing-rule)), so `int | float | bool | Decimal` reads `--ratio 3` and a file's `3.5` as `Decimal` (run), and a module that registers `Fraction` makes `--ratio 1/3` a `Fraction` only once it is imported: the candidate set would be whatever is registered at resolution time, the import dependence [no implicit subclass inference](../../architecture/design-decisions/no-implicit-subclass-inference.md#no-implicit-subclass-inference) rejected for `__subclasses__()`.
**The scalars and confarg's own registrations**, a fixed set: it splits the registry, which is one mechanism for confarg's leaves and a user's ([leaf coercion](../../architecture/types/leaf-coercion.md#leaf-coercion)), in two, and `Decimal` still takes every number under `SupportsFloat`, a UUID's text reading under `SupportsInt`.
`Enum` and `Literal` cannot be enumerated, and a collection is no scalar, so `SupportsLen` does not read a list.

### `str` and `None` join where they conform, as the other scalars do

`str` satisfies `HasUpper` and `SupportsLen`, and `NoneType` every Protocol whose members `object` provides, the four ordering methods apart ([a member inherited from object](protocol-typed-fields.md#a-member-inherited-from-object-counts-only-where-object-declares-it)): both join, so `name: HasUpper` takes any text and `x: Printable` is nullable without `| None`, a none word and a file's `null` reading `None`.
ty 0.0.93 and mypy 2.4 both accept `a: Printable = None`, `b: Empty = None`, `c: SupportsFloat = True` and `d: HasUpper = "x"`, and refuse `e: SupportsFloat = None` (run).
`bool` joins wherever `int` does, which it inherits from.

A Protocol every scalar satisfies, `Printable` or `Empty`, therefore reads as `bool | int | float | str | None`: `--label yes` is `True` and `--label 3` is `3`, exactly as the explicit union reads them, and `--label.str yes` or a file's `{__cast__: str, __value__: yes}` pins the text.

Rejected: **`str` never joining**, since it takes any text: a Protocol written for `str`, `HasUpper`, would be unreachable, with no `class:` spelling either, `builtins.str` under a tag being refused as under `Any` (`Cannot coerce dict {} to str`, [the Protocol plan](protocol-typed-fields.md#a-conforming-class-that-is-no-struct-is-built-as-under-any)).
**`None` never joining**, optionality spelled `| None` only: it is a second rule for one scalar, and a type checker accepts `None` there.
**A Protocol whose members are all `object`'s reading no scalar**, to spare `--label yes` its `True`: a second rule, and `Printable` would take no plain value though every scalar satisfies it.

### A message names the Protocol, and its own line names the scalars

`_spell_type` names a Protocol by its class name, as any class, alone and nested (`list[SupportsFloat]`).
A union refusal under it closes with the Protocol's own line, FEAT-57's demand for a tag gaining the scalars it reads, as the none-word remedy closes a union's lines ([a union refusal names each variant's reason](../../architecture/types/construction.md#a-union-refusal-names-each-variants-reason)):

```text
Cannot coerce str 'abc' to SupportsFloat at 'ratio':
  bool: cannot coerce 'abc' to bool. Valid values: ['0', '1', 'false', 'no', 'off', 'on', 'true', 'yes']
  SupportsFloat: give an int, a float or a bool, or name a class implementing it with --ratio.class
```

The `int` and `float` lines are left out as every plain refusal is (`_variant_reason`), so the Protocol's line is where the reader learns which scalars it takes.
The tag's spelling in it is the channel's, as FEAT-57 spells its demand.

Rejected: **spelling it as its union**, as an alias is ([a message names a type by what confarg reads](../../architecture/design-decisions/a-message-names-a-type-by-what-confarg-reads.md#a-message-names-a-type-by-what-confarg-reads)): `bool | int | float | str | None | Printable`, long alone and longer nested.
**The name and the union together**, `SupportsFloat (int | float | bool)`: a spelling form `_spell_type` would carry alone and nested for one kind of type.

### `--help` shows the union's flags

A Protocol field registers what its union does: the whole-value flag, whose metavar is `JSON` since the field takes a `{class: ...}` blob (`metavar="JSON" if _accepts_object_value(resolved) else "VALUE"`, as `u: int | Opts` reads `--u JSON` today), the tag flag with FEAT-57's note, and a cast flag per scalar it holds, `--ratio.int`, `--ratio.float`, `--ratio.bool`, admitted by the one rule `_cast.holds_the_cast`, which a file's `__cast__` asks too.
The adapters register no cast flag on a union with a struct variant today, while vanilla takes `--u.int 3` there: [BUG-299](../bugs/BUG-299-a-union-with-a-struct-variant-registers-no-cast-flag.md), which lands first.

Rejected: **`VALUE` for a Protocol**, the spelling users will mostly type, at the cost of a Protocol answering differently from the union it reads as; **`VALUE` for every union with a scalar variant**, `u: int | Opts` included, a wider question than this feature.

### A Protocol spreads in `_union_args`, its tag half a marker

The two canonical union readers answer for it, so every walk reads it at once — construction, the CLI walk, registration and its casts, completion, `--help`, the merge's replace-or-refine, the default layer, expressions and the dump:

- `_types._is_union(P)` answers `True` for a Protocol a scalar satisfies;
- `_types._union_args(P)` answers its scalars, in the stealing rank, then `Implementers(P)`, its tag half, and spreads a Protocol variant of a union in its place, as it spreads an alias ([a union is read flat](../../architecture/types/introspection.md#a-union-is-read-flat)): `SupportsFloat | str` is `int | float | bool | str` and `SupportsFloat`'s tag half, `SupportsFloat | float` keeps one `float`, and `SupportsFloat | SupportsIndex` keeps both tag halves.

`Implementers(P)` is a private, hashable, frozen object in `_types`: FEAT-57's struct reading of `P`.
`_resolve_type` returns it as it is, `_is_union` answers `False` for it, `_class_of` answers `P`, and `_KIND_ORDER`'s struct row classifies it `STRUCT`, so the struct predicates FEAT-57 teaches a Protocol — `_tagged_struct`, `_demands_tag`, `_struct_fields`, `_struct_subclasses`, `_union_tag_shadowed`, `_variant_holds`, `_spell_type`, the help group's heading — answer it through `P`.
The bare `P` cannot be its own tag half: `_construct_union` builds a variant through `construct(var, …)`, which would read `P` as the union again, without end.

Rejected: **a `_TypeKind` of its own**, routed per walk: ty enforces the four `match` walks, but the `_is_union` sites outside the shape dispatch (`_allows_none`, `holds_the_cast`, registration's union branch, the merge) would each learn it by hand, and each one forgotten is a parity gap.
**Rewriting the annotation where it is read** (`_struct_fields`, a container's item type, the root target): `P` stays FEAT-57's struct untouched, but every `get_args` reader would rewrite it, changing a field type's identity as the rebuild in `_resolve_type` that [a union is read flat](../../architecture/types/introspection.md#a-union-is-read-flat) rejected would.

### What follows without a decision of its own

- **Construction** offers a scalar the union's leaf rung, in the stealing rank, and a dict the tag, which FEAT-57's tag half takes; a dict with no tag is refused, since the tag half demands one ([BUG-295](../bugs/BUG-295-a-union-offers-an-untagged-value-to-a-variant-that-demands-its-tag.md)) and no scalar reads a dict.
- **The dump** asks `_variant_holds` in the variants' order, the scalars first and the tag half last, so a scalar is written by its scalar variant, bare or with the cast `_reads_back` asks for when another scalar would take it, and anything else by the tag half as FEAT-57 writes it: an implementer with its tag, a conforming value that is no struct — a `Decimal` under `SupportsFloat` — as an `Any` node writes it, with its warning.
  `dump(C())` writes `ratio: 1.0`, which loads back.
- **The default layer** lays a scalar default as any leaf default, so `${ratio}` reads `1.0`; an expression reads the scalar construction picks (`read_union_leaf`).
- **Generic Protocols** read their scalars whatever their arguments, since FEAT-57 ignores annotations: `SupportsAbs[int]` reads `bool | int | float`, and so does `SupportsAbs[str]`, a false acceptance the type checker catches.
- **A callback Protocol** reads no scalar: no scalar has `__call__` in its `__mro__` (`getattr_static(int, "__call__")` finds `type.__call__`, the metaclass's), so [FEAT-2](../features/FEAT-2-a-callback-protocol-reads-as-a-callable.md) is unaffected.
- **A tag naming a class that satisfies two Protocol variants** builds it: [BUG-300](../bugs/BUG-300-a-tag-matching-variants-of-two-classes-is-refused-as-ambiguous.md) tries the distinct bindings a tag selects in declaration order, across variant classes as `Box[int] | Box[str]` does today.

## Where it lives

| Question | Function | Asked by |
|---|---|---|
| which scalars satisfy this Protocol? | `_conformance.protocol_scalars(P)`: `class_conforms(s, P)` for each scalar, members looked up in the `__mro__`; cached weakly per Protocol, beside `protocol_members`, since the candidates are fixed and no registry is read | `_types._is_union`, `_types._union_args` |
| is this type a union, and what are its variants? | `_types._is_union`, `_types._union_args` (and `_union_args_no_none`, `_union_branches` through it) | every walk, unchanged |
| what is a Protocol's tag half? | `_types.Implementers` | `_union_args`; `_class_of`, `_spell_type` and `_KIND_ORDER` read it |
| what does the union's refusal close with? | the Protocol's demand factory on `TypeCoercionError` (FEAT-57), given the scalars spelled | `_construct._construct_union`'s refusal, where the none-word remedy is appended |

`protocol_scalars` is asked of a class `is_protocol` answered for only, under the guard `protocol_members` carries.
`_is_union` is on every walk's path, so it asks `is_protocol` first, which costs an attribute read on 3.12 and `typing.is_protocol` on 3.13+, and reads the cache only for a Protocol.

## Phases

1. **[BUG-299](../bugs/BUG-299-a-union-with-a-struct-variant-registers-no-cast-flag.md)**: the struct-union branch of `cli._build._specs_for_field` registers the union's cast flags; FEAT-59 is `blocked_by` it.
2. **[FEAT-57](../features/FEAT-57-protocol-typed-fields.md)** and what it is blocked by; FEAT-59 is `blocked_by` it.
   [BUG-300](../bugs/BUG-300-a-tag-matching-variants-of-two-classes-is-refused-as-ambiguous.md) is not a prerequisite, but a union of two Protocols is refused for a class implementing both until it lands.
3. **[FEAT-59](../features/FEAT-59-a-protocol-scalars-satisfy-reads-as-their-union.md)**, in this order, each step green before the next:
   1. `protocol_scalars`, with the `__mro__` lookup; its table as unit tests, on 3.12 and 3.13+.
   2. `Implementers`, `_is_union` and `_union_args`, `_class_of`, `_spell_type` and `_KIND_ORDER` on it; a test asks each struct predicate FEAT-57 teaches a Protocol of `Implementers(P)` and of `P` and compares the answers.
   3. The union refusal's closing line, and FEAT-57's demand message naming the scalars.
   4. The verification below through the `loader` fixture, and the user documentation.

## Verification

Each row of the tables above becomes a test against the `loader` fixture, so a file, the environment and argv reach it through all five front-ends ([testing](../../architecture/testing.md)):

- The first table, row by row, as tokens (`--x`, `APP_X`) and as a file's values: `SupportsFloat`, `SupportsIndex`, `HasUpper`, `Printable`, `HasName`.
- A file's `x: yes` under `Printable` stays `'yes'`, and `--x.str yes` is `'yes'`; `{__cast__: int, __value__: '3'}` under `SupportsFloat` is `3`, and `{__cast__: str, ...}` under it is refused, since it holds no `str`.
- `--help` of `ratio: SupportsFloat` lists `--ratio JSON`, `--ratio.class` with FEAT-57's note and `--ratio.int`, `--ratio.float`, `--ratio.bool`, on every adapter.
- `--ratio abc` is refused with the message above, its Protocol line naming the scalars and the tag as the channel spells it; under `SupportsIndex`, `--n 3.5` names `an int or a bool`.
- `{class: pkg.Impl, ...}` under `SupportsFloat` still builds a nominal and a structural implementer, and `{}` is refused for want of a tag.
- `dump(C())` and `dump_file()` of `ratio: SupportsFloat = 1.0` read back; `C(ratio=3)` dumps `3`, `C(ratio=True)` dumps `true`, `Printable` holding `'3'` dumps `'3'` bare, `C(ratio=Decimal('3.5'))` dumps with the foreign-value warning.
- `x: Printable` takes a file's `null` and `--x none` as `None`; `ratio: SupportsFloat` refuses both, the first once [BUG-298](../bugs/BUG-298-a-union-without-none-takes-a-files-null.md) has landed.
- `SupportsFloat | str`, `SupportsFloat | float`, `SupportsFloat | None`, `list[SupportsFloat]`, `dict[str, SupportsIndex]`, and a Protocol root target.
- `${ratio}` reads `1.0` with no source setting it, and `3.5` under `--ratio 3.5`.
- `SupportsAbs[int]` and `SupportsAbs[str]` read alike; a callback Protocol reads as FEAT-2 says, no scalar joining it.
- A Protocol no scalar satisfies (`HasName`) behaves as under FEAT-57, `--help` included.
- `register_leaf_type(Fraction, ...)` changes nothing a Protocol field reads.

Run the touched tests on 3.12 to 3.15, as FEAT-57's, since `is_protocol` and the member reading differ between 3.12 and 3.13+.

## What moves to the architecture notes when it lands

- A design decision, "a Protocol reads the scalars that satisfy it", carrying the decisions above with their rejected alternatives and precedents.
- [introspection](../../architecture/types/introspection.md#a-union-is-read-flat): a Protocol a scalar satisfies is a union, spread in place as an alias is, its tag half `Implementers(P)`.
- [construction](../../architecture/types/construction.md#a-union-refusal-names-each-variants-reason): the Protocol's closing line.
- [limitations](../../architecture/limitations.md): a Protocol reads no registered leaf, `Enum`, `Literal` or collection, however well it conforms; a generic Protocol's arguments are not read; a Protocol every scalar satisfies converts a token as `bool | int | float | str | None` would.
- User documentation: the README's Protocol section (FEAT-57's) gains plain values, and the stealing-rule tutorial a line on Protocols.

## Related, not part of this plan

- [BUG-298](../bugs/BUG-298-a-union-without-none-takes-a-files-null.md): a union without `None` takes a file's `null` today, so `ratio: SupportsFloat` would too until it lands.
- [FEAT-39](../features/FEAT-39-a-struct-instance-default-is-no-base.md): a Protocol field defaulting to an implementer's instance is no base; a scalar default is one already.
