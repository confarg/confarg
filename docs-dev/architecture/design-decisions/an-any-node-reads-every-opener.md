# An `Any` node reads every opener

An `Any` field reads a dict holding `class`, `classfn`, `bind` or `call` as the spec it is, as a Callable field does: `class:` builds the class it names, whatever class it is, `call:` takes its target's value as it is, `bind:` yields a partial and `classfn:` a bound method. A dict an `Any` holds is a `dict[Any, Any]` and a list a `list[Any]`, so a spec at any depth below it is read too. A bare dotted string stays a string. In a union, a tag naming no variant is the `Any` variant's spec, and a tag that does not import is refused. `dump()` writes an object an `Any` holds as the spec that rebuilds it, and keeps that form only when an `Any` node reads it back as the value it came from; anything else is written untyped, with a `ConfargWarning` ([serialization](../types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it)).

Why: files, the environment and the command line are confarg's primary channels, and before this an object could reach an `Any` field only from Python code: a field default, a dict passed to `from_dict()`, or an object built by hand. `dump()` then wrote such an object untouched, so `dump_file()` failed on it with the writer's own error, even after a plain `load()` with nothing supplied (FEAT-42). The library has not shipped, so reading the openers as data had no users to keep.

Precedent: Hydra reads `_target_` in any node of a configuration, whatever its declared type, though it builds only when the program calls `instantiate()`. jsonargparse reads `class_path` only where the annotation names a class, which is the rule this replaces.

Rejected:

- **Keep the key as data** (the [yield rule](call-yields-to-the-data-a-type-holds.md) as it stood). `Any` stays unusable for objects outside Python code, and its default objects stay undumpable.
- **Only `class:` and `call:`.** `bind:` and `classfn:` are how a function and a bound method are spelled, so an `Any` holding one could not be dumped as anything that reads back.
- **Only at the field itself.** A list of handlers below an `Any` is the common shape, and the same dict would be a spec at the field and data one key below it.
- **Read a bare dotted string as a `bind:` shorthand**, as a Callable field does. Every string an `Any` holds would be imported when it looks like a dotted path, so text such as `"a.b"` would change meaning with what happens to be importable.
- **Keep a tag that names no class as data.** A typo in a class path would become a silent dict.
- **Dump every object an `Any` holds untyped, with a warning.** The object still reaches the writer, which fails on it, and nothing a configuration spells reads it back.

Cost: a dict a program puts in an `Any` with an opener key cannot be loaded back as that dict, and `dump()` warns when it writes one. Every `Any` slot lets a file, a variable or a flag build any importable class and call any importable function ([limitations](../limitations.md#callables-and-serialization)). On the command line a key below an `Any` is typed by nothing until construction, so its flag takes one token ([callables](../callables.md#an-any-node-reads-every-opener)).
