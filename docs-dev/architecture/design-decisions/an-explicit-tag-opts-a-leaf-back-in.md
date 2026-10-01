# An explicit tag opts a leaf back in

`register_leaf_type` may not take a spelling away. Before registration a struct-shaped type is
built from its fields like any other, tag included: `{"class": "uuid.UUID", "int": 5}` produces
`UUID(int=5)` for a field typed `UUID` or `Release | UUID`. Registering `UUID` broke the plain
field — `UUID.__init__` got the dict and its `AttributeError` escaped `build()` — which is the
promise of
[a registered leaf is never a struct variant](registered-leaf-is-never-a-struct-variant.md#a-registered-leaf-is-never-a-struct-variant)
misapplied to a value that was never inferred to be a struct in the
first place. An existing configuration file is not wrong because a type it names was later
registered.

So the rule splits by who asked. A registered leaf is opaque to every **implicit** decision:
struct dispatch on a bare dict, the "struct with all-default fields is built from `{}`" shortcut
for a missing field, structural union disambiguation, tag emission on the way out
([`_is_struct_variant`](../invariants.md#delegate-to-the-canonical-function)). An **explicit**
tag naming its class asks for field construction in so many words and gets it
(`_is_taggable_leaf`). Both halves meet in `_construct_scalar`, the canonical single-value
constructor, so the tag works wherever a leaf is addressed — a plain field, a list element, a
union variant — and not just where the bug was noticed.

It reaches every *channel* too, which took a second step. Construction saw the tag wherever a
dict arrived, but on the CLI no dict arrived: the whole-value predicate asked `_is_dc`, so
`--id '{"class": "uuid.UUID", …}'` stayed a string and the JSON text was coerced into a leaf,
while the same blob in a file or an environment variable opened the class. Widening that
predicate to `_is_struct` for BUG-39 closed it — deliberately the *structural* test and not
`_is_struct_variant`, because whether the token is decoded is asked before the tag inside it
can be read ([CLI adapters](../cli-adapters/whole-value-flags.md#whole-value-flags)). `_is_struct_variant` still owns
every question construction asks afterwards; the two are not in competition.

A third step reached the hatch's *flat* spelling (BUG-56): `--id.class uuid.UUID
--id.hex …`, what the environment says with `ID__CLASS` / `ID__HEX`. Vanilla accepted it
all along — its type walk treats a registered leaf structurally, so the tag segment
resolves through the `union_tag` rule and a parameter through the leaf's `__init__`
fields — while the adapters took their `_is_registered_leaf` branch first and no flag
below the field was ever registered. The adapters' registration now mirrors the walk, argv-scanned,
and their CLI channel is the walk's own loop
([CLI adapters](../cli-adapters/whole-value-flags.md#whole-value-flags)). Argv-scanned rather than
static, unlike the whole-value flag, is the maintainer's call: a registered leaf's
ordinary spelling is its scalar, and one `--help` line per `__init__` parameter would
advertise the escape hatch at the expense of the syntax actually used — the same ground
the escaped openers are registered on. A flag naming no tag and no parameter stays
unregistered, so the framework's rejection stands in for vanilla's `no_such_field`.

An untagged dict stays an error, and the message says how to ask for fields. The rejected
alternative — let *any* dict rebuild a registered leaf from its fields, exactly as before
registration — keeps more old configurations working, but it leaves registration meaning nothing
for dict-shaped data and re-opens the introspection accident
[a registered leaf is never a struct variant](registered-leaf-is-never-a-struct-variant.md#a-registered-leaf-is-never-a-struct-variant)
closes: the
maintainer's call is that the tag is the opt-in, and nothing else is.

Precedent: nobody else lets a tag name an opaque type, but nobody else has this tag. cattrs'
`configure_tagged_union`, pydantic's discriminated unions and msgspec's tagged unions are
closed-world discriminators over modeled variants, so an opaque type cannot appear in one at
all. confarg's `class` is a dotted import path that names any class and fills its parameters
([no implicit subclass inference](no-implicit-subclass-inference.md#no-implicit-subclass-inference)); a registered leaf is a
class like another, and refusing to import it would be the special case.
