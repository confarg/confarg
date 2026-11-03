# Class names the type it builds

A `class:` spec builds exactly the class it names, whatever subclasses that class has, and so does a `classfn:` spec for the owner its path names.
Both go through `typedload._construct.construct_named_class`.
It builds through `_construct_named`, the constructor the class key calls once it has selected a variant or a subclass, and it never asks the subclass dispatch of `_construct_struct_dispatch` which subclass to build.
The spec's other keys are the class's fields: `class` among them is the opener itself, so no second class can be named beside it.

Why: `class:` is a type conversion.
The configuration asks for an `X`, and `class:` gives a compatible `Y`.
Once the spec has named `Y`, nothing is left to choose.
Running subclass dispatch on it anyway asked for a discriminator that the spec had just given, so a class with a subclass could not be named at all.
PR-63 made a struct field with subclasses demand its tag, and `class:` built its instance through that same dispatch, so `class:` broke for every class with a subclass.
`classfn:` names its owner the same way, so the two share one route.

Rejected:

- **The named class as a default that a tag key can override.**
  It kept the subclass dispatch that a custom tag reached inside a `class:` spec, when the class key's spelling was configurable ([the class key is `class`](the-class-key-is-class.md#the-class-key-is-class)).
  But one spec would then name its class twice, and the second name would quietly win over the opener.
- **A fix for `classfn:` alone.**
  The two openers would answer the same question, "build this named class from these keys", in two different ways.

Precedent: Hydra's `instantiate` calls exactly the `_target_` it is given, and jsonargparse instantiates exactly the `class_path` it reads.
Neither dispatches further once a class is named.

To build a subclass, name it under `class:`.

## A Protocol class is refused before it is called

A class a spec names must be buildable, and a `typing.Protocol` class never is: Python refuses to instantiate one whatever it is given, and its constructor is `typing`'s placeholder, whose parameters are `*args, **kwargs`.
So `_construct_named`, the constructor openers and tags share, refuses a Protocol class (`_conformance.is_protocol`) before calling anything, under `Any`, under a Callable's `class:` or `classfn:`, and for a tag, which a `@runtime_checkable` Protocol field lets name its own Protocol: "is a Protocol, so it cannot be built: name a class that implements it".
Calling it instead gave Python's `Protocols cannot be instantiated`, read as an empty call the user could fix by supplying fields, and a field supplied beside it was refused against `args` and `kwargs` (BUG-296).
A plain-class field never meets one, since a Protocol may only inherit Protocols.

Precedent: jsonargparse 4.53 refuses a `class_path` naming one wherever it meets it, `Expected an instantiatable class, but protomod.Greeter is a protocol`.
