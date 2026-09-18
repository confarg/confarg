# REF-32 — `_warn_unknown_env_field` carries a dead namedtuple branch

**Where:** `src/confarg/_parse_env.py` (`_warn_unknown_env_field`) · **Filed:** 2026-09-18
**Effort:** S · **Risk:** low · **Impact:** none

The `_is_namedtuple(root_tp)` branch (lines 277-297) is unreachable.
`_warn_unknown_env_field` is only called when `_is_struct_like(target)` is True
(see the `if not is_struct:` guard in `_parse_env`), and `_is_struct_like` is
True only for a struct or a union with a struct variant — never a namedtuple.
When `is_struct` is False a namedtuple root takes the scalar path
(`data[ROOT_KEY] = _try_coerce(...)`) and never reaches the warning, so no
caller ever passes a namedtuple as `root_tp`. Delete the branch; nothing
changes. Link:
[02-files-and-env.md#environment-parsing](../../architecture/02-files-and-env.md#environment-parsing).
