# Class names a subclass; call computes

On a typed field the `class` key is the union tag, and it names a class the annotation accepts:
a subclass of it, or the annotation itself. Any other class is refused at the field, and the
message names `call:` to say what it does: it computes a value the annotation accepts, and does
not get around the refusal. The two keys say different things: `class:` says "the type I want",
and `call:` says "compute the value".

A scalar annotation (`int`, `str`, an enum) is no struct, so the tag has no subclass to
select: a tagged dict is refused there too, naming the `class` key it refuses and pointing to
the `call:` spec (BUG-188). At that field the pointer is a remedy rather than a disclaimer:
the field takes a typed call, whose value the annotation still has to accept.

Why: a field's annotation is the contract the rest of the program reads. A `class:` that could
name an unrelated class would hand that field an object the annotation does not promise, and the
type of the built value would depend on whatever the file named. `call:` already has the
function-returns-the-value form, but it is no second spelling here: on a typed field its value
is taken only when the annotation accepts it, and anything else is built as the annotation
([call in a typed field](../callables.md#call-in-a-typed-field)), so a factory returning an
unrelated class is refused in turn.

Rejected:

- **Build any class named by `class:`.** The annotation would stop describing the field: a
  dataclass-typed field could hold an object of another shape, chosen by the file.
- **Drop `class:` on typed fields and keep only `call:`.** Subclass selection through the union
  tag is what lets one field take several structs, so removing it would break every union.

Precedent: Pydantic validates a model-typed field by `isinstance`, so an instance of an unrelated
class is refused rather than rebuilt; Hydra's `_target_` instantiates any importable class, but
its structured configs check the result against the declared type.

Cost: a user who wants a value of an unrelated class on a typed field cannot get it from the
configuration: `class:` is refused, and a `call:` spec returning it is refused in turn, so
widening the annotation — a union holding the class — is the way to it.
