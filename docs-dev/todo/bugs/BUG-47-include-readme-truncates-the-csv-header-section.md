# BUG-47 — The CSV section of `11_include` is cut off mid-sentence

**Where:** `examples/11_include/README.md:180` · **Filed:** 2026-09-27
**Effort:** S · **Risk:** low · **Impact:** none

The section on CSV inputs ends with the unfinished sentence "If the CSV contains no", followed
by a second copy of the `ints.yaml` snippet that the previous section already shows. The
sentence presumably introduced headerless CSVs: `ints_no_header.csv` and `ints_no_header.yaml`
sat in the directory unused until they were removed from the tree (recoverable from the
repository history). Finish the section — or drop the truncated sentence and the duplicate
snippet.

```console
$ grep -n "If the CSV contains no" examples/11_include/README.md
180:If the CSV contains no
```
