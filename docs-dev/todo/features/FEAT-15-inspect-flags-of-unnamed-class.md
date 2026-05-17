# FEAT-15 — No way to inspect the flags of a class the tag has not named yet

**Where:** `src/confarg/cli/_build.py` · **Filed:** 2026-09-15
**Effort:** M · **Risk:** low · **Impact:** behavior

`--help` lists a subclass's flags only once something has imported it, so a user who does not
already know a plugin's options cannot discover them
([11-limitations.md](../../architecture/11-limitations.md)). A dedicated opener would close the
gap without putting every struct's selector into `--help`: `--<field>.<union_tag>.help
<dotted.path>` imports that one class and prints its flags, the way `--<field>.<union_tag>`
already imports it to register them.

Precedent: jsonargparse registers `--<field>.help [CLASS_PATH_OR_NAME]` statically for every
subclass-typed field; given a path it imports the class and prints exactly that class's
parameters, and its sub-arguments never appear in the top-level help at all (verified,
jsonargparse 4.52.0).
