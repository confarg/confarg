# BUG-133 — An expression's list index accepts any spelling `int()` does

**Where:** `src/confarg/dictexpr/_expressions.py` (`_step`) · **Filed:** 2026-10-03
**Effort:** S · **Risk:** high · **Impact:** config

`_step` reads a path segment on a list with `int(part)`, so any string `int()` parses addresses an
element: `${xs['+1']}`, `${xs[' 1']}` and `${xs['1_0']}` read `xs[1]`, `xs[1]` and `xs[10]`. A
string subscript only means an index because a path segment is a string
([values-and-references.md#spelling-a-path](../../architecture/expressions/values-and-references.md#spelling-a-path)),
so `'1'` has to be one, but nothing asks for the lax forms. It is the expression-side sibling of
BUG-108, which tracks the same laxity in the CLI walk after BUG-97 limited a namedtuple position to
`str(i)` and `str(i - n)`. `_step` is also the dependency graph's walk (`_scan_path`) and the
write-back's, so the fix lands in one place. Fix direction: accept a list index only in a
canonical spelling (`0`, `[1-9][0-9]*`, the same with a leading `-`), which is what an integer
subscript produces. RFC 6901 (JSON Pointer) allows only `0|[1-9][0-9]*` as an array index, and
jq refuses any string index into an array.

```python
from confarg.dictexpr import resolve_expressions

for v in ("${xs[1]}", "${xs['+1']}", "${xs[' 1']}", "${xs['1_0']}"):
    try:
        out = repr(resolve_expressions({"xs": list("abcdefghijk"), "v": v})["v"])
    except Exception as exc:
        out = f"{type(exc).__name__}: {exc}"
    print(f"{v}: {out}")
# expected: ${xs[1]}: 'b', and each other spelling a MissingReferenceError: '...' is not a valid index
# actual:
# ${xs[1]}: 'b'
# ${xs['+1']}: 'b'
# ${xs[' 1']}: 'b'
# ${xs['1_0']}: 'k'
```
