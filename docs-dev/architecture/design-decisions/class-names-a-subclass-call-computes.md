# Class names a subclass; call computes

On a typed field the `class` key is the union tag, and it names a class the annotation accepts:
a subclass of it, or the annotation itself. Any other class is refused at the field, and the
message points to `call:`, which builds it through a factory it names. The two keys say different
things: `class:` says "the type I want", and `call:` says "compute the value".

Why: a field's annotation is the contract the rest of the program reads. A `class:` that could
name an unrelated class would hand that field an object the annotation does not promise, and the
type of the built value would depend on whatever the file named. `call:` already has the
function-returns-the-value form, so a value of an unrelated class needs no second spelling, only
a factory that returns it.

Rejected:

- **Build any class named by `class:`.** The annotation would stop describing the field: a
  dataclass-typed field could hold an object of another shape, chosen by the file.
- **Drop `class:` on typed fields and keep only `call:`.** Subclass selection through the union
  tag is what lets one field take several structs, so removing it would break every union.

Precedent: Pydantic validates a model-typed field by `isinstance`, so an instance of an unrelated
class is refused rather than rebuilt; Hydra's `_target_` instantiates any importable class, but
its structured configs check the result against the declared type.

Cost: a user who wants a value of an unrelated class on a typed field writes a `call:` spec that
names a factory returning it. Naming the class directly, with no factory, is refused.
