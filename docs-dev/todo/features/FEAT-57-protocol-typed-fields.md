---
filed: 2026-10-26
where:
  - src/confarg/_types.py::_tagged_struct
  - src/confarg/_types.py::_is_plain_class
  - src/confarg/_types.py::_struct_fields
  - src/confarg/_types.py::_direct_struct_subclasses
  - src/confarg/_types.py::_constructor_parameters  # typing's synthetic constructor read as object.__init__'s
  - src/confarg/_callable.py::_unproducible_return  # a Callable whose declared return is a Protocol
  - src/confarg/typedload/_coerce.py::_coerce_type_ref
  - src/confarg/typedload/_construct.py::_construct_struct_dispatch
  - src/confarg/_serialize.py::_variant_holds  # in typedload/_holding.py once BUG-293 moves it
  - src/confarg/_serialize.py::_needs_tag
  - src/confarg/cli/_build.py::_collect_struct_specs
  - src/confarg/exceptions.py::TypeCoercionError
  # and a new leaf module, src/confarg/_conformance.py
effort: L  # crosses every channel and front-end, and records two design decisions
risk: high  # the tag, construction, the type walk and the dump all change their answer at once
impact: config  # a @runtime_checkable Protocol's class tag naming a class whose method cannot be called as declared stops loading
severity: major  # a Protocol-typed field crashes with a raw TypeError; making it @runtime_checkable is a partial workaround
blocked_by: [BUG-293, BUG-294, BUG-295]  # each introduces a predicate or a refusal the Protocol branch goes into
---

# FEAT-57 — Protocol-typed fields

A field annotated with a `typing.Protocol` crashes with a raw `TypeError` at the tag, in the type walk, in `--help`, in `type[P]` and in the dump, because each site calls `issubclass` or `isinstance`, which Python refuses for a Protocol that is not `@runtime_checkable`; elsewhere a Protocol reads as a plain class whose fields are `*args, **kwargs`.

The design is settled in [the Protocol plan](../plans/protocol-typed-fields.md), which carries the decisions, the rejected alternatives, the precedents and the build order.
In short: a Protocol is an abstract base its implementers are named into with `class:`; a class conforms by having every member and calling each method as the Protocol calls it, annotations ignored; data members are checked on the built instance; `type[P]` takes a concrete class whose methods conform; the conformance rule lives in one new module and `_tagged_struct` stays the decision-maker for what a tag builds.

Callback Protocols (`__call__` only) are [FEAT-2](FEAT-2-a-callback-protocol-reads-as-a-callable.md), and a Protocol taking plain leaf values is [FEAT-59](FEAT-59-a-protocol-scalars-satisfy-reads-as-their-union.md).
