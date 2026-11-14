# Matching vanilla

## Byte-identical merged dicts

Adapters must produce the same merged dict as vanilla, byte for byte — values, and the key order a dump serializes (the contract suite checks both; `TestMergedKeyOrderContract` compares the serialized dict, since dict equality ignores order).
They do so by construction: the CLI channel is written by vanilla's own loop over the argv the framework parsed ([argv is the only writer](model.md#argv-is-the-only-writer)), so eager leaf coercion, the union shapers, the casts, the callable openers, the root `--json` fold and the order occurrences override each other in are vanilla's code, not a mirror of it.

Until REF-72 `_collect.py` mirrored each of those decisions over the framework's parse result, and the mirror drifted one decision at a time: CLI numbers stayed strings until eager coercion was mirrored (PR #99), several variants' flag was coerced by the last walk (BUG-84), and the keys followed the walk rather than argv (BUG-87).

## Expression-tolerant choice gates

Frameworks validate `Literal`/`Enum` choices at parse time, which would reject `${name}` on the CLI while env and files accept it.
Each adapter defers expression tokens via `dictexpr.contains_expression` at the point where its framework validates, keeping native help, completion and error text for real values:

| Framework | Bypass point | Why there |
|---|---|---|
| argparse | `_ExpressionTolerantChoices.__contains__` | argparse checks `value not in choices` and renders help by iterating the same object |
| click | `_ExpressionTolerantChoice.convert` | `Choice.convert` validates through a normalized mapping, not the container |
| typer | `_TypedOption.process_value` | typer ≥ 0.29 has no choice type: it validates the option's `Literal` annotation through pydantic in `process_value` |
| cyclopts | `_expression_tolerant_convert` as `Parameter(converter=…)`, and `_ExpressionTolerantPydantic` in the `Annotated` metadata | cyclopts enforces `Literal` by converting; the annotation stays for help |

`build()` validates the resolved value with the same `TypeCoercionError` everywhere.

cyclopts has a second check: whenever `pydantic` is in `sys.modules` — which any application importing pydantic anywhere puts there, typer ≥ 0.29 included — it re-validates the converter's result against the annotation through a pydantic `TypeAdapter`, and has no switch to turn that off (BUG-353).
So the annotation carries a metadata object implementing pydantic's documented `__get_pydantic_core_schema__` hook, which wraps the `Literal`'s schema to let an expression through.
confarg imports nothing from pydantic for it: pydantic finds the hook by duck typing, and calls it only when it is loaded.
Rejected: annotating the flag `Literal[...] | str` and converting against the `Literal` in the converter.
It needs no pydantic hook, but cyclopts renders the union in help as `CHOICE|STR`, where the hook leaves help, errors and completion byte-identical with or without pydantic.
