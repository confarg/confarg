# A union ranks every value

A union offers every value it reads to its leaf variants in the [stealing rank](../types/stealing-rule.md#stealing-rule): a CLI or environment token, a file's string, a native number from a file or `from_dict()`.
Declaration order only breaks ties within a rank, on every channel.
What still depends on the channel is **conversion**: only a token is converted, to a number, a bool, or `None` by a none word.
**Recognition** applies to any value: a type reference, an `Enum` member, a `Literal` member or a registered leaf takes a value it names, whoever wrote it (maintainer's choice, BUG-230).

| File value | Union | Before | Now |
|---|---|---|---|
| `"builtins.int"` | `type` | refused | `int` |
| `"builtins.int"` | `str \| type` | `'builtins.int'` | `int` |
| `"red"` | `str \| Color` | `'red'` | `Color.RED` |
| `"a"` | `str \| Path` | `'a'` | `Path('a')` |
| `5` | `int \| Level` (an `IntEnum` with a member `5`) | `5` | `Level.FIVE` |
| `"5"` | `int \| str` | `'5'` | `'5'`: a file's string is never converted |
| `"none"` | `str \| None` | `'none'` | `'none'`: only a token's none word is `None` |

## Why

- **A file could not set a `type` field** (BUG-230): `_coerce_type_ref` read only a token, so a file and `from_dict()` could not hold a class, and `dump()`'s `"builtins.int"` did not load back.
  Reading any string answers the lone field, and puts the question to `type | str`.
- **A value drifted through its own dump.**
  `--v red` on `str | Color` built `Color.RED`, `dump_file(merge(...))` wrote `v: red`, and loading that file built `'red'`: the `_StrToken` marker that told the two channels apart is what a dump drops.
  Ranking every value makes the reading depend on the value, not on the channel it came through.
- **Every losing leaf has a cast.**
  A string a variant would recognize dumps as `{__cast__: str, __value__: …}`, a vocabulary that already exists.
  Under declaration order, `str | Color` holding a member had none, which is what [FEAT-16](../../todo/features/FEAT-16-dotted-cast-names.md) was filed for.
- **It is not the Norway problem.**
  The [token model](../types/token-model.md#token-model) keeps a file's `"yes"` a string because no file value is ever *converted*; that holds.
  Recognition of a file's string was there already, in declaration order: `Color | str` read a file's `"red"` as the member.
  Only the order changed.

## Rejected

- **Declaration order for native values**, the former rule.
  It is two orders for one value, and the second one is invisible in a dump: `str | type` could not hold a class from a file, and an argv value drifted as above.
- **`str` always wins for a file's string**, pydantic v2's smart mode, where an exact type match beats a lax conversion.
  `type | str`, the natural spelling, could never hold a class from a file, and no `__cast__` names `type`, so its dump could not round-trip.
- **The rank for references only**, `type` and `Callable`, leaving `Enum`, `Literal` and registered leaves in declaration order.
  Smaller, but two rules, and the `Enum` drift stays.

## What it costs

- `str | Color` and `str | Path` read a file's string as the member or the `Path` where it used to stay text.
  A file that means the text writes `{__cast__: str, __value__: red}`, which `dump()` writes on its own.
- A string a union tries as a reference imports the module its dotted path names ([dotted imports](../types/dotted-imports.md#a-bare-word-is-never-imported), [limitations](../limitations.md#callables-and-serialization)).
- An expression reads a union's leaf as the variant construction picks ([an expression reads a typed leaf as its object](an-expression-reads-a-typed-leaf-as-its-object.md#how-each-stage-carries-it)), so the reading may import too.

## Precedents

None is one-directional. pydantic v2's smart mode orders by exactness, so a string meets `str` first, the rejected alternative above; its `left_to_right` mode and jsonargparse try members in declaration order, the former rule.
Neither has an untyped channel beside a typed one, which is what makes an order that depends on the channel drift through a dump here.
YAML 1.2's core schema resolves a plain scalar by recognition (`true`, `null`, `1.5`) whatever the reader expects, and is what the token model refuses for files; confarg recognizes only against the type the field declares.
