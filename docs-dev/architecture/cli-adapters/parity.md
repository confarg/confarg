# Matching vanilla

## Byte-identical merged dicts

Adapters must produce the same merged dict as vanilla, byte for byte (the contract suite
checks it). Therefore `_collect.py` mirrors vanilla decisions exactly: eager leaf coercion
through `_try_coerce`; single-element lists for scalar+sequence unions collapse to
`_UnionSeqToken`; a lone JSON-array token is decoded with vanilla's `_try_parse_json_list`
and stored raw; scalar casts via `_cast.resolve_forced_value`; callable specs keyed by the
active directive names from `_callable.active_directives`; root `--json` folded under
fields by `apply_root_json`. Without eager coercion, CLI numbers stayed strings and
`${base * 3}` failed (fixed in PR #99).

When no union tag is given, the collector collects the fields of **all** struct variants so
structural inference in `construct` can pick one.

## Expression-tolerant choice gates

Frameworks validate `Literal`/`Enum` choices at parse time, which would reject `${name}` on
the CLI while env and files accept it. Each adapter defers expression tokens via
`dictexpr.contains_expression` at the point where its framework validates, keeping native
help, completion and error text for real values:

| Framework | Bypass point | Why there |
|---|---|---|
| argparse | `_ExpressionTolerantChoices.__contains__` | argparse checks `value not in choices` and renders help by iterating the same object |
| click | `_ExpressionTolerantChoice.convert` | `Choice.convert` validates through a normalized mapping, not the container |
| cyclopts | `_expression_tolerant_convert` as `Parameter(converter=…)` | cyclopts enforces `Literal` by converting; the annotation stays for help |

`build()` validates the resolved value with the same `TypeCoercionError` everywhere.
