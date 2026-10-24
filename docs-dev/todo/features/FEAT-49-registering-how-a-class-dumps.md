---
filed: 2026-10-17
where:
  - src/confarg/__init__.py::register_leaf_type
  - src/confarg/_serialize.py::_serialize_struct
effort: M
needs_design: true  # the registration API, and whether it also says how the class reads back
risk: medium
impact: behavior
severity: minor  # a class whose state does not mirror its constructor cannot be dumped; dump_file(merge(...)) still saves its arguments
---

# FEAT-49 — Registering how a class dumps

`dump()` writes a plain class as its constructor's parameters, each read from the attribute the instance holds, and refuses one it does not hold ([a plain class dumps the parameters it holds](../../architecture/design-decisions/the-object-dump-writes-state.md#a-plain-class-dumps-the-parameters-it-holds)).
Correct serialization of a custom class is its author's to provide, but the only way to say how today is `register_leaf_type`, which makes the class a scalar on the way in too.
A class that keeps a parameter under another name, transforms it, or holds state beyond its parameters has no way to say "dump me as this dict, built back through my constructor".

```python
class Client:
    def __init__(self, url: str, timeout: float = 1.0) -> None:
        self._url, self._timeout = url, timeout


@dataclass
class Holder:
    client: Client = field(default_factory=lambda: Client("http://x"))


confarg.dump(Holder())
# ConfargError: Cannot serialize Client at 'client': field 'url' is declared in Client.__init__ but not
#   accessible on the instance as self.url. ...
```

The design pass decides the API (a `serialize=` beside a struct registration, or a protocol method the class defines, as pickle's `__getstate__` or pydantic's `model_serializer`), and whether the registered form must read back through the constructor.
