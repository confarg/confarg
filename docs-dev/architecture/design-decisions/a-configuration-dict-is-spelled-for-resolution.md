# A configuration dict is spelled for resolution

Every dict the API returns is a configuration, its text spelled as resolution reads it, so `$${x}` stands for the text `${x}` (maintainer-chosen, BUG-326): the merged dict as the sources wrote it, the dump through `escape_data` ([serialization](../types/serialization.md#text-spelling-an-expression-is-written-escaped)), and the resolved dict through it too.
`build()`, `load()` and a file `dump_file()` writes read such a dict through resolution; `from_dict()`, which evaluates nothing, reads each escape as its text (`dictexpr._expressions.unescape_data`) and refuses a `${...}`, whose text is not what `build()` would build.

```python
@dataclass
class C:
    f: str = ""
    x: int = 7


merged = {"f": "at $${x}"}
confarg.resolve(C, merged)  # {'f': 'at $${x}'}
confarg.from_dict(C, confarg.resolve(C, merged))  # C(f='at ${x}', x=7)
confarg.build(C, confarg.resolve(C, merged))  # C(f='at ${x}', x=7)
confarg.from_dict(C, {"f": "${x}"})  # ConfargError: The value at 'f' holds the expression ${x}, ...
```

So `from_dict(C, resolve(C, m))`, `build(C, resolve(C, m))` and a `load()` of `dump_file(resolve(C, m))` build what `build(C, m)` builds, `resolve()` gives its own result back, and `from_dict(C, dump(obj))` reads the object's text back as `build()` does.
Before, the resolved dict held its text as values: `from_dict()` read it, but `build()` and the replay dump evaluated `at ${x}` as an expression, reading whatever `x` held.

- **What `from_dict()` reads.**
  It reads the data before laying the defaults, which are the class's text and never escaped (a default `${x}` builds `${x}`, and a patch over a default combines with it as written), and after taking the local variables out, which nothing builds: a local holding a `${...}` nothing reads builds nothing wrong, and a field reading it holds the `${...}` and is refused.
  A key is read as written, since resolution reads no key; a root set whole is named as the root.
- **What stays raw.**
  `confarg.typedload.construct()` is the type layer below the expressions and no documented seam; it reads a string as it stands, and `dump()`'s read-back checks run it on the text itself.
  An argv scalar cast's `_Pinned` is opaque to both walks, as it is to resolution ([BUG-327](../../todo/bugs/BUG-327-an-argv-scalar-cast-leaves-its-expression-unresolved.md)).
- **What the walks keep.**
  Text with nothing to escape or to read is handed back itself, so an argv token (`_StrToken`) keeps the reading a union gives it by its type, and both walks share with their input every part they do not rewrite, as resolution does ([expressions](../expressions/resolution.md#resolution-copies-only-what-it-writes)).

Why: `dump_file()` cannot tell a resolved dict from a merged one, the stages hand each other plain dicts ([plain dicts between stages](plain-dicts-between-stages.md)), so the spelling has to be the dict's own.
One spelling for every dict the API returns, read alike by every reader, leaves no reader to pick.

Rejected:

- **A `dump_file()` keyword that escapes, or a public escape function** (`dump_file(confarg.escape(resolved), path)`).
  Explicit, and `resolve()` would have kept returning values, but opt-in: the plain `dump_file(resolve(...))`, the glossary's replay dump, would have stayed silently wrong, and `build(C, resolve(...))` would still evaluate the text.
- **A recorded limitation**, leaving the resolved dict to `from_dict()` alone.
- **`from_dict()` building a `${...}` as its text**, as it did: `${x}` and `$${x}` would build one text, and `from_dict(C, merged)` silently differs from `build(C, merged)` wherever the merge holds an expression.
- **Scanning the local variables too**: it refuses a dict that builds correctly.
- **Reading the escape in `construct()`**, which every construction runs, `build()`'s on resolved data and `dump()`'s read-back checks included.
- **A dict subclass marking the resolved dict**, which `dump_file()` would have escaped: a container type of confarg's own between the stages, lost on the first `dict(resolved)` or `{**resolved}`.

Cost: inspecting the resolved dict shows `$${x}` where the value is the text `${x}`; a caller's own dict handed to `from_dict()` spells such text `$${x}`, as a file does; and `from_dict()` refuses a merge holding an expression, which it used to build as text.

Precedents: OmegaConf's `to_container(resolve=True)` returns plain values, and `to_yaml(resolve=True)` writes `${x}` for a `\${x}`, which the reload evaluates (run); Hydra saves the composed configuration unresolved.
None spells its resolved output for a reload.
