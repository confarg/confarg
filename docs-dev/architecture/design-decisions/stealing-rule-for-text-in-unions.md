# Stealing rule for text in unions

Text is converted to the most specific type that accepts it, with `str` last, but only for
untyped channels ([types](../types/stealing-rule.md#stealing-rule)). Coercion happens only when
the target type allows it, so this is not the YAML "Norway problem".

The rank is **total and fixed**, and the order a union is declared in never enters into it:
`int | Decimal` and `Decimal | int` read `5` the same way, or the documented rule would only
describe half the unions it is written for. Declaration order survives as the tie-break inside a
rank, which is all it can decide without being a rule of its own
(BUG-4, closed — no link: the board holds open work only).

The rule names five kinds; the type machinery has more. **Type references, `Literal` and a
`bytes` Literal member rank together, below `Enum` and above the numbers** — maintainer's
choice. They are *recognition*, not conversion: the token has to be the name of a member of a
closed set or a class that actually imports, so a match is evidence that this variant was meant,
where coercing `5` to a float merely shows that floats accept digits. The rejected alternative
put them just above `str`, letting the numbers win every tie; it was the smaller change to
reason about but reads a `Literal["1"] | int` field's `1` as the number, discarding the one
variant that spelled that value out. Precedent: pydantic v2's smart union runs a strict pass
over every member before any lax coercion, which likewise settles `Literal["1"] | int` on the
literal.
