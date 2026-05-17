# REF-46 — Near-duplicate helper pairs in the merge core

**Where:** `src/confarg/_pipeline.py`, `src/confarg/_files.py`, `src/confarg/_parse_cli.py` ·
**Filed:** 2026-09-24
**Effort:** S · **Risk:** low · **Impact:** none

Four verified pairs remain, all the same shape — two functions that answer one question — and
all mechanical enough for one revision. Roughly 30 lines.

- `_pipeline._lookup_declared` and `_pipeline._lookup_path` are the same dict-key / list-index
  path walk, differing **only** in the sentinel returned when the path is absent (`_UNSET` versus
  `None`). One function with a `default=` parameter replaces both.
- `_files._load_csv_no_header` and `_load_csv_with_header` are parallel bodies; one function
  taking `names: list[str] | None` covers both.
- `_parse_cli._parse_json_arg` produces the same message as the `json` branch of
  `_cast.resolve_forced_value`. `_cast.py` is the canonical owner of what each cast produces
  ([03-cli-parsing.md#force-casts](../../architecture/03-cli-parsing.md#force-casts)), so the
  parser should call it. Two inline `try: json.loads(...) except JSONDecodeError` blocks in
  `_collect_append_items` and `_try_parse_json_list` are two further parse-or-None variants.
- Two token handlers in `_parse_cli.py` hand-roll a nested descent that `_merge._peek_nested` was
  written for, and whose docstring asks the caller to "keep the two in step". Bypassing it also
  skips its append-spec navigation.

Three of the original six are closed: the `_LOADERS`/`_ITEM_LOADERS` pair, the
`_load_file_item`/`_load_any` pair (with BUG-42), and the dotted-subpath nesting loop, which now
has an owner in `_files._nest`/`_mount`
([02-files-and-env.md#mounting](../../architecture/02-files-and-env.md#mounting)).
