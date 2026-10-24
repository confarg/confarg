# Token model

- `_StrToken` (a `str` subclass) marks **untyped text from a channel that carries no types**: CLI, environment, CSV/TSV cells.
  Only tokens are converted from text.
  A plain `str` came from a self-describing file and is never converted, so YAML's `"yes"` stays a string (no "Norway problem" for files).
  It is still *recognized*, as a token is, by a variant that names it — a class path, an `Enum` member, a `Literal` member, a registered leaf ([a union ranks every value](../design-decisions/a-union-ranks-every-value.md#a-union-ranks-every-value)).
- `_UnionSeqToken` (a `_StrToken`) marks a lone CLI token for a scalar+sequence union; it alone may fall back to a one-element list ([CLI parsing](../cli-parsing/token-consumption.md#unions-with-sequence-variants)).
- `_Pinned(tp, value)` carries an explicitly cast value through the merge dict; `construct` honors it before anything else, including `None` handling.
- Tokens must never leak out: an `Any` field holds a token's text, not the token (`_coerce._held_by_any`, [leaf coercion](leaf-coercion.md#leaf-coercion)), error messages print them as `str` (`_src_type`, which lives in `_types.py` beside `_StrToken` rather than in `typedload/`, so every module that formats a channel value can reach it without importing an engine — BUG-57 was the fifth site to print `type(value).__name__` instead), the dump path unwraps them in `_serialize_leaf` with `isinstance(v, _StrToken)`, and `dictexpr._map_strings` preserves the subclass when rewriting expressions.
  The test is `isinstance`, not an exact type test, so it covers the whole token hierarchy — `_UnionSeqToken` included, and any token type added later.
  Other `str` subclasses stay untouched all the same: `_StrToken` is private, so nothing a caller writes — a registered `str` leaf type included — can inherit from it, and the registry loop below the unwrap stays reachable for it.

## A leaf reaches the merged dict as written

A token is coerced before `build()` only to a value a self-describing file holds natively: `bool`, `int`, `float`, `None` and a `Literal` over them (`_coerce._is_eagerly_coercible`), so `--port 8080` holds the `int` a file's `port: 8080` does, and a CLI number works in an expression.
A token for a type whose value is an object no file holds — an `Enum` member, a registered leaf type such as `Path`, a `Literal` member that is an `Enum` — stays as typed (`_coerce._reads_as_object`), as a file's string stays as written.
So every channel delivers the same type for a leaf, and `merge()` reads back unchanged from its own dump.

Until BUG-246, `_try_coerce` also coerced an `Enum` or a registered token to the object, while a file kept its text: an expression read `Color.RED` from argv and `'red'` from a file.
Where the object is needed, an expression reads it from every channel alike ([design decisions](../design-decisions/an-expression-reads-a-typed-leaf-as-its-object.md#an-expression-reads-a-typed-leaf-as-its-object)).
