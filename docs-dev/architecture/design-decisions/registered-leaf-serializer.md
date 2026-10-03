# Registered leaf types dump through a registered serializer

`register_leaf_type(tp, coerce, *, serialize=str)` registers **both** directions, and
`_serialize_leaf` looks an instance up in `_LEAF_SERIALIZERS`. Before that, registration made
a type a leaf only on the way in: `dump_file` handed the writers an object they could not
represent, and `dump()` took the value for a struct and emitted its attributes — silent
garbage no loader reads back.

The alternative was to infer the outbound spelling as `str(value)` with no new keyword. It is
right for types whose `str()` is their wire form — `UUID`, `Decimal`, `Path` — which is why it
is the *default*, but it cannot be the only rule: `str()` of this repository's own tutorial
type (`examples/4_leaf_types`) is the `repr`-style `Int(value=42)`, which its own coercion
function refuses on the way back in. A lossy default that no user can override would have made
`dump()` quietly unusable for exactly the types registration exists to support.

Precedents: nobody infers one direction from the other. cattrs pairs `register_structure_hook`
with `register_unstructure_hook`, pydantic a validator with `PlainSerializer`, msgspec
`dec_hook` with `enc_hook`, and the standard library's `json` pairs `object_hook` with
`default=`. Registering the pair is the common shape; defaulting the second half to `str` is
confarg's concession to the common case.
