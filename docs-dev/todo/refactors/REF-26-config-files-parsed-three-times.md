# REF-26 — The `--config` files named on argv are parsed three times per run

**Where:** `src/confarg/_tags.py` (`_partial_config_from_argv`), `src/confarg/cli/_build.py`,
`src/confarg/_pipeline.py`, `src/confarg/_parse_cli.py` · **Filed:** 2026-09-15
**Effort:** M · **Risk:** low · **Impact:** none

`_partial_config_from_argv` re-reads and re-parses every file argv names, and three callers now
want the same answer independently: `build_static_flags` (to import tagged classes),
`build_dynamic_flags` (to find callable openers), and `_parse_cli` (to import tagged classes
again), before the pipeline reads the files a fourth time for their actual contents. Nothing is
wrong with the result — the reads are idempotent and only happen when `--config` is present —
but the same bytes are parsed once per caller. A small argv-keyed cache, or threading one
pre-parsed dict through the registration path, would collapse them. Grew from one caller to
three when BUG-6 closed.

**Argv itself is scanned as often, which is the other half.** Four passes per `_parse_cli` call:
`_normalize_eq_args`, then `_tags._partial_config_from_argv`, then `_tags._tags_from_argv`, then
the main loop. The adapters add `cli/_prefix.strip_argv_prefix`, `_collect_config_file_pairs` and
two more scans in `cli/_build.py`, then repeat all four inside the `patch_only` re-parse — six or
more passes for one command line.

Both `_tags` scans run on **un-normalized** argv, so each re-implements `--flag=value` splitting
and flag detection by hand rather than using `_normalize_eq_args` and `_looks_like_flag`, the sole
canonical discriminator
([03-cli-parsing.md#token-consumption](../../architecture/03-cli-parsing.md#token-consumption)).
They both want `(flag, value)` pairs and are trivially fusible into one walk over the
already-normalized token list. Also: the subpath-stripping lines in
`_parse_cli._collect_config_file_pairs` are a verbatim copy of those in `_consume_config_paths`,
so the lenient re-scan and the strict scan disagree only by accident.
