# REF-79 — Three guarded `[len(prefix):]` slices REF-56's sweep missed

**Where:** `src/confarg/_parse_cli.py`, `src/confarg/_tags.py`, `src/confarg/_types.py` ·
**Filed:** 2026-10-03
**Effort:** S · **Risk:** low · **Impact:** none

The removeprefix sweep that closed REF-56 enumerated four sites and missed three more of the
same shape — each inside an explicit `startswith` guard, so `removeprefix` is exact:

- `_parse_cli.py` `_config_subpath` — the `key[len(config_flag) + 1 :]` branch is
  `key.removeprefix(f"{config_flag}.")`. The sibling fallback `return key[len(config_flag) :]`
  is **not** a candidate: it is unguarded, cutting `len(config_flag)` characters whether or not
  *key* carries the flag, and must keep its slicing spelling.
- `_tags.py` — `path_str = tok[len(flag_prefix) + 1 :]` under
  `elif tok.startswith(f"{flag_prefix}=")` is `tok.removeprefix(f"{flag_prefix}=")`.
- `_types.py` `_base_declares_path` — `path[len(head) :].split(...)` is
  `path.removeprefix(head).split(...)`; the guard is the `path.startswith(head)` operand of the
  same `and`. *head* is `""` without a prefix, where both spellings return *path* unchanged.

Found while fixing REF-56; all three verified on the parent revision. The suite covers each
path (env and CLI config flags, BUG-86's subclass registration), so the swaps are `S`, `low`.
