# REF-63 — `13_collection_items` carries an empty section and a misplaced tuple remark

**Where:** `examples/13_collection_items/README.md:356` · **Filed:** 2026-09-27
**Effort:** S · **Risk:** low · **Impact:** none

`## From environment variables` is a heading with no body — the next line is the next
heading. `12_collections` already defers the environment-variable discussion to a later
tutorial, so the heading likely belongs to that deferral and should either get its content or
go. In the same file, the sentence "Its fixed length is known from the type, so negative
indices count from the end here too" introduces an example that also builds a `list[int]`,
whose length is not known from the type; the paragraph after the example then scopes negative
indices to tuples. Move or reword so the remark introduces the tuple example it describes.
