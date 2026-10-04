# BUG-127 — The anchor sweep skips a citation that names a document without an anchor

**Where:** `docs-dev/todo/anchors.py` · **Filed:** 2026-10-04
**Effort:** S · **Risk:** low · **Impact:** none

`_CITATION` requires `#<anchor>`, so a `Dev Notes:` entry that cites only a document
(`docs-dev/architecture/locals.md`, which `_pipeline.py`, `_defaults.py` and `exceptions.py` all
do) is never looked at: if the document is renamed or deleted the citation goes stale and the
sweep still reports success. Present on the revision before BUG-105 was fixed too. Fix direction:
match the anchor as optional and check that the document exists whether or not an anchor
follows.

```console
$ printf '"""x.\n\n    Dev Notes:\n        docs-dev/architecture/09-invariants.md\n"""\n' > src/confarg/_probe.py
$ uv run python docs-dev/todo/anchors.py
51 document(s) cited, every anchor resolves
# expected: exit 1, "src/confarg/_probe.py:4: cites docs-dev/architecture/09-invariants.md, but there is no such document"
# actual:   exit 0 — the document does not exist and nothing is reported
$ rm src/confarg/_probe.py
```
