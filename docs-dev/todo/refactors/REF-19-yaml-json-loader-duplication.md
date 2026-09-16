# REF-19 — YAML/JSON dict loaders duplicate their item-loader counterparts

**Where:** `src/confarg/_files.py` (`_load_yaml`/`_load_yaml_item`, `_load_json`/`_load_json_item`)
· **Filed:** 2026-09-13
**Effort:** S · **Risk:** low · **Impact:** none

Each pair duplicates the optional-import guard, the `FileNotFoundError` → `not_found` mapping, and
the parse-error → `malformed` mapping; the only difference is that the dict variant enforces
`isinstance(data, dict)`. Extract `_read_yaml_raw(path)` / `_read_json_raw(path)` returning the raw
top-level value; the dict wrappers become one-liners (`data = _read_yaml_raw(path); return data if
isinstance(data, dict) else {}`). Removes ~30 lines of repeated error mapping.
