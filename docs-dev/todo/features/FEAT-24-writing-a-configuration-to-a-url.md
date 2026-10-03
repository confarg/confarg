# FEAT-24 — Writing a configuration back to a URL

**Where:** `src/confarg/_files.py` (`_DUMPERS`, `_dump_file`), `src/confarg/_sources.py`, `src/confarg/_api.py` (`dump_file`) · **Filed:** 2026-09-26
**Effort:** M · **Risk:** low · **Impact:** behavior

Reading a configuration accepts any registered scheme; writing one does not. `dump_file()` still
takes a filesystem path, `_DUMPERS` still dispatches on `Path.suffix`, and each dumper opens the
path itself — the shape the readers had before locations existed
([02](../../architecture/config-files/locations-and-schemes.md#locations-and-schemes)).

The symmetric design is a second registry of writers, `bytes` in rather than out, and
`register_scheme` growing an optional `write=` argument so one call can describe both directions —
the way `register_leaf_type` registers a coercion and a serializer together
([10](../../architecture/design-decisions/registered-leaf-serializer.md#registered-leaf-types-dump-through-a-registered-serializer)).
`_dump_file` would then serialize to bytes and hand them to the writer, mirroring
`_loader_for` + `_read_bytes`.

Two questions are open and need the maintainer:

- **Is a scheme that can only read acceptable?** A handler registered for reading would not gain
  a writer, so `dump_file()` to that scheme must fail with something better than a missing-key
  error. Alternatively `write=` is mandatory, which breaks every read-only handler.
- **What does a partial write mean?** A local dump truncates and rewrites; an object-store or
  HTTP write is one request that either lands or does not, and a failed `PUT` may leave a
  previous version in place. That difference is user-visible and belongs in
  [11](../../architecture/limitations.md#remote-sources) whichever way it is settled.

Wanted for the case where a program reads its configuration from a bucket, resolves it, and
writes the resolved form back beside it as a record of what actually ran.
