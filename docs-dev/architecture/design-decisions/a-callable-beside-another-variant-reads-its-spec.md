# A Callable beside another variant reads its spec

A union holding a Callable and another variant builds the Callable from each spelling of a spec ([callables](../callables.md#a-callable-beside-another-variant), BUG-234). Before, it never did: a string was tried on the Callable as a scalar leaf, which resolves no spec, a `class:` dict was read as the struct tag only, and `bind:` reached no variant at all. Four choices settle where each spelling goes; each is the maintainer's.

## A string meets the Callable in rank, just below type references and `Literal`

A Callable takes anything callable, classes included, so it ranks below the kinds that recognize a narrower set: a class for a type reference, listed members for a `Literal`. `Callable | type` reads `pkg.Mul` as the class, whichever side the Callable is written on, and `Callable | Literal["print", "log"]` reads `print` as the member. It ranks above the numbers and `str`, which no import can reach: no bool word, number or none word names a callable in `builtins`.

Rejected: **sharing the rank with type references and `Literal`**, so that declaration order breaks the tie. No new rank, but `Callable | type` read a class as a factory and `type | Callable` as the class, the very dependence on declaration order the [stealing rule](stealing-rule-for-text-in-unions.md#stealing-rule-for-text-in-unions) removed.

A bare word in `builtins` is a reference like any other, so `Callable | str` reads `help` or `format` as the builtin. A file that means the text writes `{__cast__: str, __value__: help}`, and `dump()` writes that itself; dropping the builtins fallback in a union, or everywhere, was rejected to keep `--value int` working ([dotted imports](../types/dotted-imports.md#dotted-imports)).

## A dict holding an opener is the spec before it is any variant's data

`{bind: …}` and `{classfn: …}` go to the Callable variant before a struct or a dict variant tries them, unless a struct variant owns the opener's key, the rule a member owning the union tag's spelling already follows ([real field wins](../cli-parsing/casts-and-reserved-words.md#real-field-wins)). The union tag still selects a struct variant it names first, and a class no struct variant holds is the Callable's `class:` spec, as it was an `Any` variant's. An `Any` variant follows the same order, after a Callable when the union has both: `Any | dict[str, str]` reads `{bind: pkg.f}` as the function.

Rejected: **the Callable tried last, as the `Any` variant was**. It matched the existing `Any | dict` behavior, but a `dict[str, str]` variant would take `{bind: pkg.f}` as two strings, and `Callable | dict[str, Any]` could never read a spec at all. Opener-first is also what the merge already assumed: `reads_as_new_value` read an opener in such a union as replacing what lies below, which construction then read as data. The two now ask one function, `spec_reading_variant`.

## A `call:` is the union's to take

A `call:` runs once, and its value is taken as a typed call takes it on any field: as it is when a variant accepts it, a callable by the Callable variant, else built as the union. `Callable | Opts` takes `{call: pkg.make_double}` as the function and `{call: pkg.make_opts}` as the `Opts`, which each struct variant had already taken as its own typed call.

Rejected: **the Callable owns `call:`**, so the value must be callable, as on a lone Callable field. One rule for every opener, but it broke the factory of a struct variant, which worked.

## A path that names nothing is a refusal; a module that fails is not

A variant whose path imports nothing lets the next variant read the string: `pkg.dubble` in `Callable | str` is text. A module that exists and fails while importing stops the union, as on a lone field ([dotted imports](../types/dotted-imports.md#a-path-names-nothing-or-a-module-fails)).

## What it costs

- A typo'd path in `Callable | str` silently becomes text, and in `Callable | Opts` it fails without naming the import ([FEAT-46](../../todo/features/FEAT-46-a-union-refusal-names-each-variants-reason.md)).
- `Any | dict` reads an opener-keyed dict as a spec, where it used to be the dict variant's data.

## Precedents

jsonargparse resolves a `class_path` dict in a union by trying each member in order, and accepts a callable's dotted path wherever a `Callable` member is; pydantic's `ImportString` imports a path wherever it is declared, and in a union smart mode prefers an exact `str` match. Hydra reads `_target_` before anything else in the node, whatever the annotation, which is the opener-first order without the struct-owns-the-key exception.
