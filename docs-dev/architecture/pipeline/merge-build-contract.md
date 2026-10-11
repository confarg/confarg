# Merge build contract

`merge()` returns an **unvalidated** dict: it is not guaranteed to be constructible into the
target. Convertibility is decided only in `build()`/`construct()`, which raise
`TypeCoercionError`/`MissingFieldError`.

- Parsers reject only what they can **prove wrong at parse time** (a flag missing its value,
  an empty `--flag` for a union whose only sequence variant is a fixed tuple, invalid JSON
  after an explicit `.json` cast). A config file or env var carrying `"abc"` for an `int`
  merges cleanly and fails in `build()`.
- **Do not add convertibility validation to the merge layer.** It would make channels
  disagree (a CLI check that env/files skip) and it cannot see expression results.
- The merge layer is **type-unaware; `build()` is type-aware.** When the right behavior
  depends on the type, the merge layer defers instead of guessing:
  - an index patch past the end of a base list (`--input.2 3` over `[1, 2]`) is an error for a
    `list` but fills a slot for a fixed `tuple`, so `_merge_list_base` carries the base as
    `{"*": base, "2": 3}` and lets construction decide;
  - a key that is no index over a base list (`--pt.x 9` over a file's `pt: [1, 2]`) names a
    field of a namedtuple but nothing in a list, so `_merge_list_base` carries it the same way,
    `{"*": [1, 2], "x": 9}` (BUG-160). Both deferrals are one question,
    `_merge._patch_needs_the_type`; a patch that also appends or deletes is a list operation
    and is still refused in the merge. Deferring changes who applies the patch, never what it
    means: construction refines each position the base holds through the merge's own
    combiner, `_merge._merge_existing_value`, as the merge would have (BUG-164);
  - `_parse_cli._resolve_field_type` returns a field type only when all union variants agree,
    otherwise `str` (the raw token is stored, coerced in `construct`), on the CLI and env
    channels alike.
- Expressions are the extreme case: their value is unknown until `build()`. See
  [expressions](../expressions/deferral-rule.md#deferral-rule).
