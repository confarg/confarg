# No custom types required

Plain dataclasses, NamedTuples, plain classes, unions and standard annotations work with no
base class, decorator or field marker; confarg is "not a framework" and its footprint in user
code is a few lines. Break this only for important features that cannot be done otherwise.

- Cost: all knowledge comes from runtime introspection, concentrating complexity in `_types.py`
  and `typedload`. Per-field extras (help, metavar) ride on `Annotated[T, FieldMeta(...)]`, which
  is stdlib and invisible at runtime.
- Precedents: pydantic-settings and Hydra structured configs require their own base classes or
  containers; jsonargparse and cyclopts also introspect plain signatures/dataclasses.
