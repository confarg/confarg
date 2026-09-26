# REF-56 — Seven `[len(prefix):]` slices that are `str.removeprefix`

**Where:** `src/confarg/cli/_collect.py`, `src/confarg/cli/_prefix.py`,
`src/confarg/cli/_build.py`, `src/confarg/_parse_env.py`, `src/confarg/_parse_cli.py` ·
**Filed:** 2026-09-24
**Effort:** S · **Risk:** low · **Impact:** none

Each of these sits inside an explicit `startswith` branch, so `removeprefix` is exact:

- `cli/_collect.py:277` — `tail = k[len(flag_prefix) :]` (guard on line 276)
- `cli/_collect.py:302` — `k[len(prefix) :].split(".")` (guard on line 301)
- `cli/_prefix.py:103` — `stripped[key[len(dot_pfx) :]] = value` (guard on line 102)
- `cli/_prefix.py:133` — `token[2 + len(dot_pfx) :]` → `token[2:].removeprefix(dot_pfx)`
  (guard on line 130)
- `_parse_cli.py:490` — `raw_key[len(dot_pfx) :]` (guard on line 489)
- `_parse_env.py:408` — `key[len(prefix) :].removeprefix(separator)`, which already calls
  `removeprefix` for the *second* half of the same expression. This one is the argument for the
  sweep: the two spellings sit on one line.

Worth its own line, because it is the one carrying arithmetic rather than a bare `len`:
`cli/_build.py:1061`, `subpath = name[len(config_flag) + 1 :]` → `name.removeprefix(f"{config_flag}.")`.
The `+ 1` stands for the dot, and hand-counted offsets are what `removeprefix` exists to retire.

Ruff does not flag any of these: `FURB188` matches only the ternary spelling
(`x[len(p):] if x.startswith(p) else x`), never the `if`-statement form used here.
