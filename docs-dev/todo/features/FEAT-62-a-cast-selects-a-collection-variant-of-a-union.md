---
filed: 2026-11-05
where:
  - src/confarg/_cast.py
  - src/confarg/typedload/_construct.py::_try_pinned_dict
  - src/confarg/_parse_cli.py
  - src/confarg/_serialize.py::_serialize_union
effort: L
needs_design: true  # what a cast may name, and how a flag and a variable spell it
risk: medium  # the cast reads every channel; a collection cast is new only where the name is a collection
impact: behavior  # a value no spelling reached builds, and dump() writes it with its cast
severity: minor  # a value is refused or warned about, and reordering the union or tagging the items is the workaround
---

# FEAT-62 — A cast selects a collection variant of a union

No spelling selects a collection variant of a union, so a value an earlier variant finds ambiguous cannot reach it: `list[Cat | Dog] | list[dict[str, str]]` refuses a list of dicts ([an ambiguity met inside a variant ends the walk](../../architecture/types/construction.md#an-ambiguity-met-inside-a-variant-ends-the-walk), [limitations](../../architecture/limitations.md#subclasses)).
A cast is the escape hatch for the same problem on a leaf, and a cast naming the collection, `{__cast__: "list[dict[str, str]]", __value__: […]}`, would do it, on all three channels as a cast does today, with `dump()` writing it where the bare value would not read back.
That also answers the case `dump()` can only warn about today, a collection variant another variant takes back ([a stolen leaf dumps with its cast](../../architecture/design-decisions/a-stolen-leaf-dumps-with-its-cast.md#a-stolen-leaf-dumps-with-its-cast)).

What the design pass has to settle:

- **What a cast names.**
  A cast names a scalar or a registered leaf ([a cast names a type the field holds](../../architecture/design-decisions/a-cast-names-a-type-the-field-holds.md#a-cast-names-a-type-the-field-holds)), by a closed list a typo fails against.
  Spelling a collection needs a parser of type expressions, or an index into the union's variants, and `_spell_type`'s text is what a message already shows.
- **Parity.**
  `--pets.list[dict[str, str]] '[…]'` is no flag a shell likes, and `detect_force_cast` reads a closed suffix set, so the flag and the variable need a spelling of their own ([cross-channel parity](../../architecture/invariants.md#cross-channel-parity)).
- **Items below the cast.**
  Whether the named variant alone is built, the union no longer asked, which is what a cast promises.
- **`Any`.**
  Whether a collection cast also pins a container an `Any` variant holds ([limitations](../../architecture/limitations.md#casts)), which a bare `S | Any` holding `{a: 1}` cannot read back today.

Related: [FEAT-16](FEAT-16-dotted-cast-names.md), which widens what a cast names along another axis.
