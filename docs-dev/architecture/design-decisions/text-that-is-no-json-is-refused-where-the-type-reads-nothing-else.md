# Text that is no JSON is refused where the type reads nothing else

A `{`- or `[`-led value on argv or in the environment is decoded as JSON where the type it lands at reads the object or the array it opens, and read as text anywhere else, a whole value and an item alike ([token consumption](../cli-parsing/token-consumption.md#a-json-led-value-is-read-by-its-type)).
When it is no JSON, what it becomes hangs on the type's other variants, `None` aside:

| Field | `'{"x": 1,'` (`'[1,'` for a sequence), on argv or in the environment |
|---|---|
| `dict[str, int]`, a struct, either one optional | `Invalid JSON for --d: Expecting property name …`, `Invalid JSON for APP_D: …` |
| `list[int]`, `tuple[int, int]` | `Invalid JSON for --xs: Expecting value …` |
| `str \| dict[str, int]` | the text `'{"x": 1,'` |
| `Path \| dict[str, int]` | `Path('{"x": 1,')` |
| `int \| dict[str, int]` | the union's refusal, with `dict[str, int]: invalid JSON: Expecting property name …` on its line |

Where every variant reads the shape the text opens, no reading of it builds the field, so the parser refuses it, naming the flag or the variable: a typo in a JSON value is never silently something else.
Where a variant may take text, the text goes to construction, which picks the variant as it does for any token, and carries its decode error (`_types._IllFormedJson`): should no variant take it, the union's refusal gives that error as the reason of the variant reading the shape (maintainer-chosen).

Until BUG-323 the channels disagreed.
argv refused every `{`-led value that was no JSON wherever an object was taken, and the environment read every one as text, so `APP_U='{"x": 1,'` built `u='{"x": 1,'` where `--u` was refused, and `APP_D` failed as `expected dict, got str`.
A `[`-led one was an item on argv and text in the environment.

Precedents (run): jsonargparse 4.53 reads the text at a `str | dict` field on both channels and refuses it at a `dict`; pydantic-settings reads it as text at a `str | dict` field from the environment and refuses it on its CLI, the split confarg had.
Both hand the text to every other variant, a `Path` included, not only to `str`, and both refuse an ill-formed array at a list field.

## Rejected

- **Refusing it wherever a variant reads the shape**, argv's former rule, carried over to the environment: `{`-led text could then reach a `str | dict[str, int]` field from no channel but a file, the `.str` cast being a dict key there.
- **Reading it as text everywhere**, the environment's former rule: `--d` would trade `Invalid JSON` for `expected dict, got str`, which hides that the value was meant as JSON.
- **Only a `str` variant taking the text**: the parser would answer which variant takes a value, which is construction's question, and `Path | dict` would refuse what both precedents read.
- **Storing the plain text** for construction: `int | dict` would be refused as `Cannot coerce str '{"x": 1,' to int | dict[str, int]`, nothing saying the value was meant as JSON.
- **A one-element list from a `[`-led token**, which `_UnionSeqToken` builds from any other lone token at a scalar-or-list union: `bool | list[str]` would read `--x '[a b]'` as `['[a b]']` where `list[str]` refuses it, so a scalar variant beside the list would change what the list reads (maintainer-chosen).
- **Decoding a `{`-led item whatever its type**, as an appended item was: an `Any` reads a whole `{`-led value as text, and an item is read as a whole value of its type is (maintainer-chosen).
  jsonargparse decodes such a value at an `Any`, pydantic-settings does not (run).

## What it costs

- A lone `[`-led token at a list is its whole value, so `--tags '[a b]'` is refused at a `list[str]`, where it was the item `'[a b]'`; `--tags+ '[a b]'`, `--tags '["[a b]"]'` or a run of two tokens writes it.
- An appended `{`-led item at a `list[Any]` is text, where it was an object; `--xs '[{"a": 1}]'` writes the object.
- The refusal at a union names the field's path (`at 'n'`), not the flag or the variable, being construction's.
- On a repeated flag the refusal of a lone token waits for the end of argv, since a later occurrence makes it an item, so an error a later flag raises comes first.
