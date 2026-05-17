---
filed: 2026-10-10
where:
  - src/confarg/_types.py
  - src/confarg/typedload/_construct.py
  - src/confarg/cli/_spec.py
  - src/confarg/_serialize.py
effort: M  # the design pass: four open points, each answerable from the existing union and patch machinery
risk: high  # construction is shared by every channel
impact: behavior
severity: minor  # workaround: widen the annotation and normalize in __post_init__
needs_design: true  # the effort sizes the design pass; the implementation is not sized
---
# FEAT-40 — A field accepts a wider input than the type it holds

A recurring shape: `size: tuple[int, int]` should also take a bare `3`, meaning `(3, 3)`; `transform: Transform` should also take a handle into an application registry, `"resize"`. The only per-field way today is to widen the annotation to `tuple[int, int] | int` and `Transform | str` and normalize in `__post_init__`. The built object then claims a type it never holds, and every consumer pays in `isinstance` checks to satisfy the type checker.

What exists falls short:

- `register_leaf_type(Transform, lookup)` covers the registry case, but globally, and it makes `Transform` opaque: an untagged dict is refused ([a registered leaf is never a struct variant](../../architecture/design-decisions/registered-leaf-is-never-a-struct-variant.md#a-registered-leaf-is-never-a-struct-variant)).
- It cannot cover `size`: a `tuple[int, int]` key is ignored, since the fixed-arity shape dispatch claims the field first, and it would apply to every such field anyway.
- A `call:` spec (`size: {call: pkg.square, args: {n: 3}}`) works on any field, but asks the user to spell the conversion at every use.

Parsing is not the gap. `tuple[int, int] | int` already reads `--size 3` and `--size 3 4` alike. What is missing is a way to separate the type a field *accepts* from the type it *holds*.

## Sketch

`Annotated` metadata, which keeps [no custom types required](../../architecture/design-decisions/no-custom-types-required.md#no-custom-types-required) and is read the way `FieldMeta` is:

```python
@dataclass
class Config:
    size: Annotated[tuple[int, int], Accepts(int, lambda n: (n, n))]
    transform: Annotated[Transform, Accepts(str, TRANSFORMS.__getitem__)]
```

- Every channel parses and constructs against `T | X` through the existing union machinery ([leaf coercion](../../architecture/types/leaf-coercion.md#leaf-coercion)). When an `X` variant wins, `f` turns it into the value.
- `T` stays accepted, so `dump()` writes `T`'s own form and reads back without an inverse function, unlike `register_leaf_type`'s `serialize=`.
- Type checkers see `T`. `Config(size=3)` in Python stays an error, which is right: only confarg's channels widen the input.
- Field-local: other `tuple[int, int]` fields are untouched, and `Transform` stays constructible from a tagged dict.
- Help and metavar show `T | X`.

## Open points for the design pass

1. `X` explicit (`Accepts(int, f)`), or inferred from `f`'s first parameter annotation as attrs and tyro do.
2. A collection patch (`--size+ 5`, a `ListOp`) against a value still in its `X` form: run `f` before patching, or refuse.
3. Whether `f`'s result is checked to be a `T`.
4. One canonical accessor for the input type, read by introspection (`_type_kind`), the CLI spec and construction alike ([invariants](../../architecture/invariants.md#delegate-to-the-canonical-function)).

## Precedents

| Library | Mechanism | Is the input type declared? |
|---|---|---|
| attrs | `field(converter=f)`; the mypy plugin and pyright derive the `__init__` parameter type from `f` | inferred from the converter |
| dataclasses | PEP 712 `field(converter=)`, rejected by the Steering Council in 2024 | — |
| pydantic v2 | `Annotated[T, BeforeValidator(f)]`; `json_schema_input_type=` was added later for the schema | added afterwards |
| tyro | `Annotated[T, tyro.conf.arg(constructor=f)]`; the CLI is built from `f`'s signature | through `f`'s signature |
| cyclopts / typer | `Parameter(converter=)` / `Option(parser=)` | no, CLI tokens only |
| cattrs / msgspec / jsonargparse | global per-type hooks | per type, not per field |
| serde (Rust) | `#[serde(try_from = "Raw")]`, `deserialize_with` | an explicit `Raw` type |

pydantic and tyro show that a converter alone is not enough here: confarg's CLI arity, help, completion and environment coercion all parse against the input type, so the type must be visible rather than hidden inside a function.

Related: [FEAT-6](FEAT-6-annotated-field-metadata.md) reads `Annotated` metadata in all three channels and is the natural home of the accessor; [FEAT-21](FEAT-21-app-supplied-expression-functions.md) is an expression-side route to a registry; [FEAT-14](FEAT-14-dataclass-fields-outside-init.md) is the `InitVar` route some users take today.
