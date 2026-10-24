---
filed: 2026-10-17
where:
  - src/confarg/_types.py::_constructor_parameters
  - src/confarg/_types.py::_init_fields
effort: M
needs_design: true  # how a forward is detected (source reading, a declared marker, MRO), and its limits
risk: high
impact: config  # --kwargs.n becomes --n
severity: minor  # --kwargs.n sets it, untyped
---

# FEAT-50 — A `**kwargs` forwarded to the parent sets the parent's members

A struct's members are its constructor's parameters ([a dataclass is read by its `__init__`](../../architecture/design-decisions/a-structs-members-are-its-constructors-parameters.md#a-dataclass-is-read-by-its-__init__)).
A subclass whose own `__init__` takes `**kwargs` and passes them to `super().__init__` is therefore set through a `kwargs` dict, untyped: `--kwargs.n 2` builds `n='2'`.
For an undecorated subclass of a dataclass that is a regression of FEAT-14, which used to read the parent's fields and accept `--n 2`; for a plain class it was always so.

```python
@dataclass
class Parent:
    n: int = 1


class Child(Parent):
    def __init__(self, extra: str = "e", **kwargs):
        super().__init__(**kwargs)
        self.extra = extra


confarg.load(Child, argv=["--extra", "x", "--n", "2"], env={})
# UnknownArgumentError: Unknown argument: '--n' (field 'n' not found); --kwargs.n 2 gives n='2'
```

Precedent: jsonargparse resolves a `**kwargs` forwarded to `super().__init__` by reading the class's source, and reads `--x.extra y --x.n 2` as `{n: 2, extra: 'y'}` for a dataclass parent and a plain one alike.
The design pass decides how a forward is detected and what a `**kwargs` that goes elsewhere stays.
