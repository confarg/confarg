---
filed: 2026-09-15
where:
  - src/confarg/_tags.py::_partial_config_from_argv
  - src/confarg/cli/_build.py
  - src/confarg/_pipeline.py
  - src/confarg/_parse_cli.py
  - src/confarg/_parse_env.py::_env_config_pointers
  - src/confarg/_parse_cli.py::_config_pairs_in
  - src/confarg/_parse_cli.py::_argv_named_nodes
effort: M
risk: low
impact: none
severity: minor  # a --config URL is fetched twice per run
---

# REF-26 — The `--config` files named on argv are parsed three times per run

`_partial_config_from_argv` re-reads and re-parses every file argv names, and three callers now want the same answer independently: `build_static_flags` (to import tagged classes), `build_dynamic_flags` (to find callable openers), and `_parse_cli` (to import tagged classes again), before the pipeline reads the files a fourth time for their actual contents.
Nothing is wrong with the result — the reads are idempotent and only happen when `--config` is present — but the same bytes are parsed once per caller.
A small argv-keyed cache, or threading one pre-parsed dict through the registration path, would collapse them.
Grew from one caller to three when BUG-6 closed.
FEAT-32's `_parse_cli._typed_call_openings` read them once more in `_parse_cli` and once more in `build_dynamic_flags`, until a computation's arguments moved under `args` and the scan went with it.

**A location can now be a URL, so each of those reads can be a network fetch.**
Two per run for a root `--config` URL (the pre-scan, then the pipeline), and the same for every `__include__` inside it.
Nothing is incorrect — the rule that nothing is cached across configurations is deliberate ([11](../../architecture/limitations.md#remote-sources)) — but it raises the value of collapsing the passes from tidiness to latency.
Since BUG-259 one configuration reads each location once, keeping its document in what the configuration has read (`_files.Reads`), which the pipeline threads; the pre-scans open their own, so handing them the pipeline's would collapse their reads into its.

**Argv itself is scanned as often, which is the other half.**
Four passes per `_parse_cli` call: `_normalize_eq_args`, then `_tags._partial_config_from_argv`, then `_tags._tags_from_argv`, then the main loop.
The adapters add `cli/_prefix.strip_argv_prefix`, two more scans in `cli/_build.py` (and cyclopts' pre-parse refusal through `_config_pairs_in`), then run all four again in the loop that writes their CLI channel — six or more passes for one command line.

Both `_tags` scans run on **un-normalized** argv, so each re-implements `--flag=value` splitting and flag detection by hand rather than using `_normalize_eq_args` and `_looks_like_flag`, the sole canonical discriminator ([cli-parsing/token-consumption.md#token-consumption](../../architecture/cli-parsing/token-consumption.md#token-consumption)).
They both want `(flag, value)` pairs and are trivially fusible into one walk over the already-normalized token list.

**The naming feature (BUG-233, BUG-236) added passes of its own, and left two return values dead.**
The config level now loads before argv and the environment are typed, so the pairs are found ahead of the loops: `_parse_cli._config_pairs_in` scans argv for `--config` before vanilla's loop, `_parse_cli._argv_named_nodes` scans it again for the nodes it names, and `_parse_env._env_config_pointers` reads the environment for `CONFIG[__subpath]` before `_parse_env`.
The loops still collect the same pairs as they meet them, and nobody reads them: every caller of `_parse_cli` takes `[0]` or nothing (`_api._merge`, `cli/_collect._merge_from_flat`, `cli/_build._collect_loop_typed_specs`), and `_pipeline._lower_layers` writes `env_data, _ = _parse_env(...)`.
Each `--config` subpath is therefore checked by `_check_mount_subpath` twice, once in `_config_pairs_in` and once in the loop.
Collapsing the passes includes dropping the second return value of both loops — or having the loop be what `_config_pairs_in` calls, so the pairs and the check have one source.

**On the adapter path the whole config level is read twice, at registration and at the merge.**
`populate_*` reads the layers below argv to type the flags (`_pipeline.below_argv`): every `files=` file, the `env_config` file, the `CONFIG__*` mounts and argv's `--config` files, with a `Reads` of its own, then the merge reads them all again.
The environment must be read again at the merge (a variable set after the parser is built is read, [the adapters](../../architecture/design-decisions/a-node-types-its-keys-by-the-class-it-names.md#the-adapters)); the files have no such liveness argument, so a `Registration` carrying the config level it loaded would halve the reads, weighed against FEAT-47's question of what a stateful object caches.
