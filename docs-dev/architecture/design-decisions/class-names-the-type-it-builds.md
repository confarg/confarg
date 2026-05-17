# Class names the type it builds

A `class:` spec builds exactly the class it names, whatever subclasses that class has, and so
does a `classfn:` spec for the owner its path names. Both go through
`typedload._construct.construct_named_class`. It builds a struct with `_construct_struct`, the
route a union tag takes once it has selected its class, and it never asks the subclass
dispatch of `_construct_struct_dispatch` which subclass to build. A union-tag key among the
siblings would name a second class, so it is refused as an unknown field, unless the named
class declares a field of that spelling. The key only reaches construction when `union_tag`
is not `class`: under the default, a plain `class` is the opener itself, and an escaped spec
refuses a plain `class` sibling as a mixed form.

Why: `class:` is a type conversion. The configuration asks for an `X`, and `class:` gives a
compatible `Y`. Once the spec has named `Y`, nothing is left to choose. Running subclass
dispatch on it anyway asked for a discriminator that the spec had just given, so a class with
a subclass could not be named at all. PR-63 made a struct field with subclasses demand its
tag, and `class:` built its instance through that same dispatch, so `class:` broke for every
class with a subclass. `classfn:` names its owner the same way, so the two share one route.

Rejected:

- **The named class as a default that a tag key can override.** It would keep the subclass
  dispatch that a custom `union_tag` reaches inside a `class:` spec today. But one spec would
  then name its class twice, and the second name would quietly win over the opener.
- **A fix for `classfn:` alone.** The two openers would answer the same question, "build this
  named class from these keys", in two different ways.

Precedent: Hydra's `instantiate` calls exactly the `_target_` it is given, and jsonargparse
instantiates exactly the `class_path` it reads. Neither dispatches further once a class is
named.

Cost: with a custom `union_tag`, a tag key beside `class:` no longer selects a subclass of the
named class. To build the subclass, name it under `class:`.
