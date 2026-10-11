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
closed). A class nested in a *function* has no path under either spelling: its qualified name
holds `<locals>`, and a tag naming it is imported like any other, so it is refused at `dump()`
([below](#a-dotted-path-is-written-only-when-it-imports-back)). Writer and reader now sit in the
same module, side by side.

A bound method is the one object whose qualified name is not its path: `Sub().m` has the
`__qualname__` `Base.m` when the base defines `m`. `dotted_name` therefore spells a bound
method as its owner's path plus `__name__`, the owner being the class it is bound to (the
instance's class, or the class itself for a class method), as `pickle` reduces a bound method
to its `__self__` and `__name__`.

A failure raised *inside* an importable module is kept distinct from "this prefix is not
a module": only a `ModuleNotFoundError` whose `name` is the prefix itself or one of its
ancestors means the prefix is simply not importable (try a shorter one). Any other failure
raised while loading the module — a broken transitive dependency, a failed
`from x import y`, a circular import — comes from a module that does exist and is surfaced
as `SymbolImportError` rather than swallowed and masked as a typo'd path. The discriminator
is `ModuleNotFoundError.name`, because `ImportError` is the shared base of "module not
found" and "module found but its imports failed".

## A dotted path is written only when it imports back

`dotted_name` spells a path; it does not promise one leads back. A class or a function defined
in a function has `<locals>` in its qualified name, a lambda `<lambda>`, and a module may hold
another object under the name. So a dump imports the path it is about to write, through
`imports_back`, and refuses at `dump()` what would otherwise fail only on read-back (BUG-193):
a class tag or a `type[X]` leaf through `_serialize._class_path`, and a callable in
`_serialize_callable`, which models auto-binding on top
([callables](../callables.md#a-path-is-written-only-when-it-reads-back)).
The comparison is `is`, or `==` for a class method, which is a new bound method on each access.
Precedent: `pickle`'s `save_global` looks the qualified name up in its module and refuses an
object it does not find there as itself ("not the same object as").
