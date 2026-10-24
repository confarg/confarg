# Dotted imports

`_import_dotted` tries the longest importable module prefix of a dotted path, then `getattr` for the rest, then falls back to `builtins` so `int`, `str`, … need no prefix (this is what makes `--value int` work for `str | type`).
An undotted name goes to `builtins` alone, never to an import ([below](#a-bare-word-is-never-imported)), so a builtin name and a module of the same name never meet.

`dotted_name` is the inverse and the **one writer**: every dotted path confarg emits — a union class tag, a `type[X]` leaf, a callable spec, the class names listed in an error — comes from it.
It spells `__qualname__`, never `__name__`, because that is what `_import_dotted` resolves back: a class nested inside a class is reached as `Outer.Inner`, and a tag naming it `Inner` is unloadable.
The reason the function exists rather than the f-string being repeated is that the divergence is silent and asymmetric — the writer picked `__name__`, the reader `__qualname__`, and `dump()` emitted a tag its own `from_dict()` could not read (BUG-41, closed).
A class nested in a *function* has no path under either spelling: its qualified name holds `<locals>`, and a tag naming it is imported like any other, so it is refused at `dump()` ([below](#a-dotted-path-is-written-only-when-it-imports-back)).
Writer and reader now sit in the same module, side by side.

A bound method is the one object whose qualified name is not its path: `Sub().m` has the `__qualname__` `Base.m` when the base defines `m`.
`dotted_name` therefore spells a bound method as its owner's path plus `__name__`, the owner being the class it is bound to (the instance's class, or the class itself for a class method), as `pickle` reduces a bound method to its `__self__` and `__name__`.

A failure raised *inside* an importable module is kept distinct from "this prefix is not a module": only a `ModuleNotFoundError` whose `name` is the prefix itself or one of its ancestors means the prefix is simply not importable (try a shorter one).
Any other failure raised while loading the module — a broken transitive dependency, a failed `from x import y`, a circular import — comes from a module that does exist and is surfaced as `SymbolImportError` rather than swallowed and masked as a typo'd path.
The discriminator is `ModuleNotFoundError.name`, because `ImportError` is the shared base of "module not found" and "module found but its imports failed".

## A path names nothing, or a module fails

The two failures are two exceptions.
`SymbolNotFoundError`, a subclass of `SymbolImportError`, says nothing answers to the path: no module prefix imports, the attribute chain breaks, or the string is no dotted path of identifiers at all.
A plain `SymbolImportError` says a module on the path exists and failed while it was imported.
Every `except SymbolImportError` still catches both, as `except ImportError` catches the `ModuleNotFoundError` the subclass is modelled on.

A union needs the difference (BUG-230).
A reference variant that finds nothing has refused the value, and the next variant reads it: `"hello"` in `type | str` is the text.
A module that fails stops the union instead, as it stops a lone field: the path names real code that is broken, and holding it as text would hide the failure until the string is used as a class.
`_coerce_type_ref` turns the first into the `TypeCoercionError` the union's variant loop skips, and re-raises the second with the field's path, which the loop does not catch.

The syntactic check comes first because `importlib.import_module` refuses an empty or a relative name with a `ValueError` or a `TypeError`, which the broken-module branch used to report as `error loading module ''`: under that reading, `type | str` would have refused the empty string.
A string with a space, a slash or an empty part never reaches the import machinery.

## A bare word is never imported

An undotted name is looked up in `builtins` and nothing else.
What an import of it could yield is a module, which is no class and no callable, so every reader refuses it; the import could only run the module's top level.
Before BUG-230 it did, for every word a union with a reference variant tried: `"this"` printed the Zen of Python, `"antigravity"` opened a browser.
Ranking a file's strings too would have extended that to every file value in a `type | str` field.
A dotted string still imports the module its path names, which is what recognizing a reference by import costs ([limitations](../limitations.md#callables-and-serialization)); pydantic's `ImportString` and Hydra's `_target_` import the same way.

## A dotted path is written only when it imports back

`dotted_name` spells a path; it does not promise one leads back.
A class or a function defined in a function has `<locals>` in its qualified name, a lambda `<lambda>`, and a module may hold another object under the name.
So a dump imports the path it is about to write, through `imports_back`, and refuses at `dump()` what would otherwise fail only on read-back (BUG-193): a class tag or a `type[X]` leaf through `_serialize._class_path`, and a callable in `_serialize_callable`, which models auto-binding on top ([callables](../callables.md#a-path-is-written-only-when-it-reads-back)).
The comparison is `is`, or `==` for a class method, which is a new bound method on each access.
Precedent: `pickle`'s `save_global` looks the qualified name up in its module and refuses an object it does not find there as itself ("not the same object as").
