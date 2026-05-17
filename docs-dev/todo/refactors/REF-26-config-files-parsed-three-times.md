# REF-26 — The `--config` files named on argv are parsed three times per run

**Where:** `src/confarg/_tags.py` (`_partial_config_from_argv`), `src/confarg/cli/_build.py`,
`src/confarg/_pipeline.py` · **Filed:** 2026-09-15
**Effort:** M · **Risk:** low · **Impact:** none

`_partial_config_from_argv` re-reads and re-parses every file argv names, and three callers now
want the same answer independently: `build_static_flags` (to import tagged classes),
`build_dynamic_flags` (to find callable openers), and `_parse_cli` (to import tagged classes
again), before the pipeline reads the files a fourth time for their actual contents. Nothing is
wrong with the result — the reads are idempotent and only happen when `--config` is present —
but the same bytes are parsed once per caller. A small argv-keyed cache, or threading one
pre-parsed dict through the registration path, would collapse them. Grew from one caller to
three when BUG-6 closed.
