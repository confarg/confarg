# REF-60 — Nothing asserts the bytes `dump_file` writes

**Where:** `tests/test_serialize.py` (`dump_file` tests), `src/confarg/_files.py`
(`_dump_yaml`, `_dump_json`) · **Filed:** 2026-09-26
**Effort:** S · **Risk:** medium · **Impact:** none

Every `dump_file` test is a round trip: write the file, `load()` it back, compare the objects. No
test ever reads the bytes on disk, and a round trip through the library's own reader is insensitive
to how they were written. So the four deliberate choices in the writers are unpinned — each of
these leaves the whole suite green (4197 passed, 1 skipped), verified one at a time:

| Mutation | Real effect |
|---|---|
| `yaml.dump(data, f, Dumper=yaml.SafeDumper)` → `yaml.dump(data, f)` | the default `Dumper` emits Python-specific tags |
| `open("w", encoding="utf-8", newline="\n")` → drop `encoding` | locale encoding; cp1252 on Windows |
| `open("w", encoding="utf-8", newline="\n")` → drop `newline` | CRLF on Windows |
| `json.dump(data, f, indent=2)` → `indent=3` or dropped | the file's shape changes |

The encoding and newline pairs are spelled identically in `_dump_yaml` and `_dump_json`, and both
copies survive. Two of the four are **platform-dependent**, so CI on `ubuntu-latest`
(`.github/workflows/ci-test.yml`) structurally cannot catch them: on Linux UTF-8 is already the
default and `newline` changes nothing. They bite only on Windows, which is where a tool writing
CRLF goes unnoticed until the next `--all-files` run — the concern of REF-29, recorded in
[the decision that pinned line endings](../../architecture/design-decisions/line-endings-pinned-in-gitattributes.md).

Fix direction: one test per writer that asserts the bytes, not the round trip — `read_bytes()`
contains no `\r`, non-ASCII content survives, and the JSON file's indent is the declared one. That
also makes `SafeDumper` observable, by dumping a value whose default-Dumper output would carry a
`!!python/` tag.

Mutation scores for context: `_serialize.py` 77% (95 survivors of 404) and `_files.py` 77% (126 of
567, 19 mutants still unmeasured); the writers are the part of both that no assertion reaches.
