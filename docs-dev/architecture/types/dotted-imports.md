# Dotted imports

`_import_dotted` imports the module prefixes of a dotted path shortest first and keeps the longest that is a module, then `getattr` for the rest, then falls back to `builtins` so `int`, `str`, … need no prefix (this is what makes `--value int` work for `str | type`).
An undotted name goes to `builtins` alone, never to an import ([below](#a-bare-word-is-never-imported)), so a builtin name and a module of the same name never meet.

`dotted_name` is the inverse and the **one writer**: every dotted path confarg emits — a union class tag, a `type[X]` leaf, a callable spec, the class names listed in an error — comes from it.
It spells `__qualname__`, never `__name__`, because that is what `_import_dotted` resolves back: a class nested inside a class is reached as `Outer.Inner`, and a tag naming it `Inner` is unloadable.
The reason the function exists rather than the f-string being repeated is that the divergence is silent and asymmetric — the writer picked `__name__`, the reader `__qualname__`, and `dump()` emitted a tag its own `from_dict()` could not read (BUG-41, closed).
A class nested in a *function* has no path under either spelling: its qualified name holds `<locals>`, and a tag naming it is imported like any other, so it is refused at `dump()` ([below](#a-dotted-path-is-written-only-when-it-imports-back)).
Writer and reader now sit in the same module, side by side.

A bound method is the one object whose qualified name is not its path: `Sub().m` has the `__qualname__` `Base.m` when the base defines `m`.
`dotted_name` therefore spells a bound method as its owner's path plus `__name__`, the owner being the class it is bound to (the instance's class, or the class itself for a class method), as `pickle` reduces a bound method to its `__self__` and `__name__`.

## A C type's method is named through its class

A method of a C type has no `__module__`: `str.upper`, `dict.get` and `datetime.datetime.isoformat` are method descriptors, `int.__add__` and `object.__init__` slot wrappers, `dict.fromkeys` and `datetime.datetime.now` builtin class methods.
A Callable field takes each from its path and keeps it as it is ([auto-binding](../callables.md#auto-binding)), so `dump()` has to write that path back.
`dotted_name` names it as it names a bound method, its owner's path plus `__name__`, the owner being the class Python records: a descriptor's `__objclass__`, a builtin class method's `__self__` (`_import._c_owner`).
So `str.upper` dumps as `builtins.str.upper`, as `len` dumps as `builtins.len`, and the path is checked like any other before it is written ([below](#a-dotted-path-is-written-only-when-it-imports-back)).
Until BUG-195 `_serialize_callable` wrote a path only for a callable with a `__module__`, and refused every one of these as a callable "with no dotted path" it had itself built.

Two C callables have no class to be named through.
A C static method (`str.maketrans`, `bytes.maketrans`) has `None` for `__self__`, and before 3.15 no `__module__` either; 3.15 gives it `builtins`, and it dumps from there.
A C method bound to an instance (`"abc".upper`) is bound to a value no spec builds, since `classfn:` opens no C method ([classfn names an instance method](../design-decisions/classfn-names-an-instance-method.md)).
Both are refused at `dump()` ([limitations](../limitations.md#callables-and-serialization)).

Rejected: reading the owner off `__reduce__`, which is how `pickle` writes all of them, a C static method included (`str.maketrans.__reduce__()` is `(getattr, (str, 'maketrans'))`).
It would close the gap three `maketrans` methods leave before 3.15 by leaning on the pickle protocol rather than on the attributes `inspect` documents; 3.15 closes it on its own.
jsonargparse's `get_import_path` refuses every C type's method.

A failure raised *inside* an importable module is kept distinct from "this prefix is not a module": only a `ModuleNotFoundError` whose `name` is the prefix itself means the prefix is simply not importable, and the walk stops there; its ancestors all imported before it, so none of them can be the module not found.
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

The module that fails is the one the message names.
The prefixes are imported shortest first, so the first import that raises is that module's own: `pkg.sub.Thing` with a broken `pkg/__init__.py` reports `error loading module 'pkg'`, and a broken `pkg/sub.py` `error loading module 'pkg.sub'`.
Every ancestor of a module is a module, so the walk can stop at the first prefix that is not one; it imports what the longest-first walk imported, and resolves every path as it did.
That walk named the prefix it was trying, `brokenmod.Thing`, since `import_module("brokenmod.Thing")` runs `brokenmod` on the way (BUG-256).
A failure inside a module the path's module imports names the path's module, as a missing dependency always did: the user wrote that one, and the module that raised is in the chained cause and the traceback.
`pkgutil.resolve_name`, `pydoc.locate` and Hydra's `_locate` walk shortest first too; `pydoc` names the path's module the same way (`problem in brokenapp`).
Rejected: keeping the longest-first walk and importing the ancestors again on a failure to find the culprit, which runs a failed module's top level twice, since a failed import leaves nothing in `sys.modules`.

A `RecursionError` or a `MemoryError` raised during the import passes through as it is.
Nothing tells whether the module's own code raised it or the caller's stack ran out a few frames below the limit, and wrapping it named a sound module as broken (`error loading module 'freshmod.Thing': maximum recursion depth exceeded`), the relabelling [catching `RecursionError` at the public functions](../design-decisions/a-configuration-nests-at-most-64-levels.md#rejected) was rejected for.
A module that recurses at its top level loses its name from the message; its frames stay in the traceback.
Every reader that catches `SymbolImportError` lets it through the same way, the dump's reads-back check (`imports_back`) and the auto-binding test (`_callable._instance_method_owner`) included, where it used to read as a path that does not import back.
`pkgutil.resolve_name` and jsonargparse's `import_object` let it out raw; `pydoc.locate` wraps it.

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

## A tag is a dotted path

One function reads a class tag, `_callable._import_class_by_path`, for the four places one is written: a union's and a struct field's under the union tag, and a `class:` spec on an `Any` node or a Callable field, under the key `class` whatever the union tag.
The tag is text, the spelling every channel shares; any other value, a number, a list, a null or a class object `from_dict()` was handed, is refused naming the key and the path, as `call:` and `bind:` refuse a target that is no text (BUG-235).
A `type[X]` field takes a class object, since its value is the class; a tag only names the class to build.
A path that names nothing is a `TypeCoercionError` and a module that fails while it is imported a `SymbolImportError`, both naming the tag and the path, as a `type` field tells them apart ([above](#a-path-names-nothing-or-a-module-fails)).

Until BUG-235 two functions read a tag.
The `Any` node and the Callable field imported the path themselves, so a tag that is no string escaped as Python's `AttributeError`, and an unimportable one as a bare `SymbolNotFoundError` naming no field; the union's reader wrapped a module that fails into the `TypeCoercionError` a typo gets.
The pre-readers that import a tag before construction (`_tags._tag_named_struct`, `_tags.import_tagged_classes`) leave every failure to it, a tag that is no string included.
