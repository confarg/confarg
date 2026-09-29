# Dotted imports

`_import_dotted` tries the longest importable module prefix, then `getattr` for the rest,
then falls back to `builtins` so `int`, `str`, … need no prefix (this is what makes
`--value int` work for `str | type`). It assumes no builtin name collides with an
importable module name.

`dotted_name` is the inverse and the **one writer**: every dotted path confarg emits — a
union class tag, a `type[X]` leaf, a callable spec, the class names listed in an error — comes
from it. It spells `__qualname__`, never `__name__`, because that is what `_import_dotted`
resolves back: a class nested inside a class is reached as `Outer.Inner`, and a tag naming it
`Inner` is unloadable. The reason the function exists rather than the f-string being repeated is
that the divergence is silent and asymmetric — the writer picked `__name__`, the reader
`__qualname__`, and `dump()` emitted a tag its own `from_dict()` could not read (BUG-41,
closed). A class nested in a *function* survived either spelling, because such a tag is matched
against `__subclasses__()` rather than imported, which is why the bug went unnoticed. Writer and
reader now sit in the same module, side by side.

A failure raised *inside* an importable module is kept distinct from "this prefix is not
a module": only a `ModuleNotFoundError` whose `name` is the prefix itself or one of its
ancestors means the prefix is simply not importable (try a shorter one). Any other failure
raised while loading the module — a broken transitive dependency, a failed
`from x import y`, a circular import — comes from a module that does exist and is surfaced
as `SymbolImportError` rather than swallowed and masked as a typo'd path. The discriminator
is `ModuleNotFoundError.name`, because `ImportError` is the shared base of "module not
found" and "module found but its imports failed".
