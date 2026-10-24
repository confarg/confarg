# An expression reads a typed leaf as its object

A leaf whose value is an object no configuration file holds — an `Enum` member, an instance of a registered leaf type (`Path` among them), a `Literal` member that is one — reaches the merged dict **as it was written**, on every channel, and an expression reads it **as its object**, wherever one type is certain.
What an expression leaves behind is that object's **dump form**, never its `str()`.
So the four places a value can come from agree:

| `p: Path = Path("/a")`, `c: Color = Color.RED` (`RED = "red"`), set by | `merge()` holds | `"${c}@${p}"` | `${c == other}` | `${p / 'sub'}` |
|---|---|---|---|---|
| the default | nothing (laid at `build()`) | `red@/a` | `True` | `Path('/a/sub')` |
| argv `--p /b --c RED` | `'/b'`, `'RED'` | `red@/b` | `True` | `Path('/b/sub')` |
| env `X_C=red` | `'red'` | `red@…` | `True` | — |
| a file `c: red` | `'red'` | `red@…` | `True` | — |

Before BUG-246, argv, env and the default delivered the object and a file the text, so the first three rows interpolated `Color.RED@\b` on Windows, `${c == 'red'}` flipped with the channel, and `${p / 'sub'}` failed from a file only.
The channels disagreed on the **types they could reach**; fixing that, rather than patching each expression feature, is what makes every expression agree.

## How each stage carries it

- **`merge()`** holds what was written.
  `_try_coerce` coerces a token eagerly only to a value a file holds natively — `bool`, `int`, `float`, `None`, a `Literal` over them (`_is_eagerly_coercible`); a token for a type whose value is an object (`_reads_as_object`) stays as typed, as a file's string stays as written ([token model](../types/token-model.md#a-leaf-reaches-the-merged-dict-as-written)).
  `merge()` stays a document: it reads back unchanged from its own dump.
- **`build()` and `resolve()`** read the leaf as its object (`_typed_read.TypedReading`, the read hook they give `resolve_expressions`): the type at a position is the one the typed merge steps to (`TypedAt`, reading the tag or spec each node holds), and `_coerce.read_as_object` coerces the value there where that type, an optional included, is one `Enum`, registered or `Literal`-over-`Enum` type.
  A union of several variants reads the value as the variant construction picks (`_construct.read_union_leaf`, the same ranked walk construction takes): as the object where that variant is one of those types, as written otherwise.
  `Any` and a base with untagged subclasses keep the value as written.
  Until BUG-230 a union kept it as written too, the rule `_try_coerce` applies to tokens, so `${a == b}` was `False` for an `a: str | Color` built as the member `b` holds; the merge cannot pick a variant, but the reading runs at `build()`, where construction can.
  A value the type refuses is read as written, for construction to refuse.
  The reading applies on every read: a source's value, an earlier expression's result, every leaf of a subtree ([values and references](../expressions/values-and-references.md#a-typed-leaf-reads-as-its-object)).
- **What an expression leaves** — a pure result, an interpolated piece, a computed subscript key — is its dump form (`_serialize.written_form`: an `Enum` member's value, a registered type's serializer).
  `resolve()` rewrites only what expressions produced, so a source's `RED` comes out as `RED`, and its dict stays one a writer accepts.
- **`dictexpr.resolve_expressions`** knows no type: without the hooks, called directly or by nothing that has a target, it reads and writes values as they are.
  `from_dict()` resolves nothing.

## Why objects inside, dump form at the edges

An object is the one value every spelling and every channel agree on: `RED`, `red`, `Color.RED` and a YAML `1` for an `IntEnum` are one member, a quoted and an unquoted number are one `Decimal`.
Arithmetic needs it (`${price * 2}` on a `Decimal`, `${p / 'sub'}`), and so does a comparison between two fields.
Text is needed only where a value leaves the computation: an interpolation, the data `resolve()` returns, a key it looks up.
There the object takes the form `dump()` writes, which is what a file holds and reads back.

## Rejected

- **Reading every leaf as written** ("file form" everywhere).
  No stage gains a type, but the value then depends on the spelling, not the meaning: `lvl: 1` and `lvl: LOW` compare differently, and `price: 9.99` computes while `price: '9.99'` repeats the string.
- **Canonical text**: coerce, then hand the expression the dump form.
  Every spelling reads the same, but a type that dumps as a string computes as one, so `Decimal` arithmetic is silently string repetition everywhere.
- **Objects, written with `str()`** (OmegaConf).
  Simpler, but an interpolation writes `Color.RED` and the OS's separators, a pure `${c}` refuses to build a `str` field, and `resolve()` returns objects no writer accepts.
- **Coercing a file's value during `merge()`** where a token is coerced (OmegaConf/Hydra, jsonargparse).
  It would converge too, but `merge()` would stop being "as written" for files, every registered coercer would run on every file's value, overridden ones included, and the merge — type-unaware by contract except to decide replace or refine ([merge build contract](../pipeline/merge-build-contract.md#merge-build-contract)) — would read the type for a second question.
- **Recording it as an approved divergence.**
  It contradicted `_try_coerce`'s own purpose, "consistent types regardless of source".

## What it costs

- A plain `Enum` member compares equal to nothing a configuration can spell: `${c == 'red'}` is `False` on every channel.
  Two enum fields compare; a `StrEnum` or an `IntEnum` compares with its value ([limitations](../limitations.md#expressions)).
- An expression's result is text in the resolved data: `v: Any = "${c}"` builds `'red'`, as it did from a file, where argv and the default used to give the member.
- A registered type's coercer also runs when an expression reads its leaf, besides construction.
- A subtree holding such a leaf is substituted as a copy, not as the live sub-dict ([values and references](../expressions/values-and-references.md#referencing-a-whole-subtree)).

## Precedents

OmegaConf 2.4 and Hydra coerce a YAML `red` or `RED` into an `EnumNode`'s member as the data merges, and interpolate it with `str()` (`Color.RED@\a` on Windows, measured); `to_yaml` writes an enum by name and a `Path` as a `!!python/object/apply` tag. jsonargparse parses file values into typed `Path` objects.
Terraform, Helm and Jsonnet keep paths as strings joined by interpolation (`"${path.module}/files"`), and Kubernetes CEL sees a CRD's enum as its string. confarg takes the typed value from the first group and the written form from the second, each where it is needed.
