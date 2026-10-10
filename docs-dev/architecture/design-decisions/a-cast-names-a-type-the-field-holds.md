# A cast names a type the field holds

A cast — a CLI `.str`/`.int`/`.float`/`.bool` suffix, or a file's `{__cast__, __value__}` pin
— is admitted only where its named type is one of the types the field's annotation holds:
the field's own type for a leaf, one of its variants for a union, anything for `Any`. A
cast naming anything else is refused, on every channel and every front-end alike:
`--u.int 5` at a `tuple[int, int]` field and a file's `u: {__cast__: int, __value__: 5}` at
the same field are both refused, and so is an int pinned at a `str`, a list, a struct or an
enum field. A cast may still disambiguate among the field's variants — that is the escape
hatch's whole job, `--v.str FOO` at `Color | str` — but it may never place a value the
field's type does not accept: the configuration object that is returned must respect the
field annotations provided as input ([invariants](../invariants.md#contracts)).

**One predicate owns the admission.** `_cast.holds_the_cast` answers it.
`_parse_cli.detect_force_cast` asks it, so vanilla's parse, the adapters' registration and
their parse refuse the same spellings. It asks it of each branch the walk reaches at the field, never of the branches' fold: two variants typing the field differently fold to `str`, which would refuse `--u.x.int 5` where the variant the tag picks holds `int` and its file pin is admitted (BUG-214);
`construct()` asks it of a pin, so a file's
`__cast__` and a stored `_Pinned` a hand-built `merge()` supplied are covered too. The gate
in `_constructStruct` exempts the pin spelling from reading a defaulted fixed-sequence
field's dict as an index patch, so a pin is read the same way whether the field carries a
default or not (BUG-210). Registration offers exactly what the rule lets through: a plain
leaf's own cast, and a union's own scalar variants (BUG-94); the "non-obvious stealing"
heuristic is gone, because the admission rule is the whole rule.

- Rejected: registering the cast flags wherever vanilla accepted them (BUG-93's and
  BUG-94's preferred direction, with BUG-72's registration for leaves as the precedent).
  The maintainer refused it: a cast that pins a value the field's type does not accept is
  unacceptable in any channel, so widening registration would have spread the escape
  instead of closing it.
- Rejected: refusing only at `build()`, leaving the flag accepted at parse. The refusal had
  to come before the framework parses, as the adapters' registration always has, so the
  channels agree at one point in time; `construct()` still guards, because a merged dict
  can be built by hand.
- Precedents: argparse's `type=` callable decides the value a flag yields, and no spelling
  makes a field hold a value its annotation does not accept; pydantic-settings validates a
  CLI-parsed value against the field's type and fails the run on a mismatch *(inferred)*.
- Cost: a `Literal`'s stealing cannot be disambiguated — `Literal["16", 16]` steals the
  token `"16"` to `16`, and `--u.str 16` is refused because `str` is not the field's type,
  even where the coerced value would have been a member. The value-level check that would
  admit it was refused: it coerces before it refuses, so the error the user meets is the
  field's own rather than a message naming the cast. A file written before the rule that
  pins a type its field does not hold now fails to load, by design.
