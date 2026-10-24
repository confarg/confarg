---
filed: 2026-10-24
where:
  - src/confarg/typedload/_construct.py::_construct_union
  - src/confarg/typedload/_construct.py::spec_reading_variant
  - src/confarg/typedload/_construct.py::opener_reader
---

# Q-9 — Should a struct-owned opener beside `args` reach the Callable?

On a union holding a Callable and a struct variant that owns an opener's name, `Callable[[int], int] | Hook` where `Hook` has a field `bind`, the key is the struct's data ([a Callable beside another variant](../../architecture/callables.md#a-callable-beside-another-variant)): `{bind: pkg.add}` builds `Hook(bind='pkg.add')`.
But `{bind: pkg.add, args: {y: 3}}` builds the Callable's `partial(add, y=3)`, from a file, `--h.bind pkg.add --h.args.y 3` or across layers alike.
No rule says so: `Hook` refuses the unknown field `args`, and the union tries its next variant, the Callable, which reads the dict as a spec.

The other readers of the same dict disagree with that outcome.
`spec_reading_variant` answers no variant for both dicts, so the merge's `reads_as_new_value` takes both as `Hook`'s data that a later layer refines, and registration, which asks `opener_reader` since BUG-274, lists `--h.bind` as `Hook`'s field and describes no `--h.args.<p>` from the target.

The options:

- **Keep the fall-through and document it**: a struct-owned opener is the struct's unless the struct refuses the dict, then the Callable's spec.
  The merge and registration would have to read `args` beside the owned key as the spec's too, so all three agree.
- **Refuse it**: the owned key is the struct's whatever lies beside it, so `{bind: x, args: …}` is `Hook` refusing `args`, which names the field and the struct.
  The partial is then spelled through a tag the struct cannot take, or by renaming the field.

Precedents to weigh: pydantic's smart union tries each member and keeps the first that validates, the fall-through; a discriminated union refuses instead.
