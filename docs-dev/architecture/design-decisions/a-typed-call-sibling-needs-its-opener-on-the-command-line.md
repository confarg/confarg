# A typed call's sibling needs its opener on the command line

`--n.call pkg.f --n.x 4` on a field `n: int` is `{n: {call: pkg.f, x: '4'}}`, in all five
front-ends. The `call` key itself, in either form, is a spec wherever construction would
dispatch it (`typedload._construct._takes_typed_call`), so it is a `str` subtree like a
Callable field's `bind`. A sibling that names no member, such as `--n.x`, is accepted only
where the command line opens a call at `n`: a flag below its `call` key, a key of a whole
`{…}` value, or a key of a root `--config` file that argv names. The order on the command line
does not matter. `_parse_cli._typed_call_openings` gives the answer, and the type walk reads it
(`_walk_path(..., calls=…)`). Vanilla's loop and the adapters' registration both ask it, so
any flag one accepts, the other registers.

Why: a Callable field holds a spec whatever it is given, so everything below it can be
accepted. A field of any other type holds a spec only when a call opens it, and accepting
every key below every typed field would turn `--port.typo 3` and `--db.hots x` into
`build()` errors on every front-end. With the opener scan, a typo below a field that no call
opens stays the parse error it was, as an unknown flag always is
([strict CLI, lenient environment](strict-cli-lenient-environment.md)).

The root is excluded: with no `cli_prefix`, a host framework's own flags sit at the root
beside confarg's, and the adapters skip a flag whose first segment names no member. A root
`call` would claim the host's flags once opened. A typed call at the root is spelled in files.

Rejected:

- **Accept any key below a field that could hold a call**, as the environment already does.
  This is the simplest rule, and the environment's own leniency is the precedent for it. But
  it gives up parse-time typo detection below every typed field on every front-end.
- **Leave typed calls to files and the environment** and spell only a Callable field's
  nested target spec on the CLI. This would keep a channel gap that FEAT-27's grammar promises
  to close.
- **Read the opener from the merged lower layers** (the environment, `config_files=`) as
  well. The adapters register their flags at `populate_*` time, before those layers are
  known, so vanilla would accept flags that the frameworks reject.

Precedents: jsonargparse discovers a subclass's `--model.init_args.*` flags from the
`class_path` given on the same command line. Hydra refuses an override of a key that its
structured config does not declare unless the key is added explicitly (`+db.extra=1`), so an
undeclared key needs an explicit spelling before it is accepted.

Cost: a call opened only by the environment, by a `config_files=` file or by a
`--config.<path>` mount cannot be refined from flags
([limitations](../limitations.md#callables-and-serialization)). Parsing reads the root
`--config` files argv names one more time, best effort, as the union-tag import scan already
does ([REF-26](../../todo/refactors/REF-26-config-files-parsed-three-times.md)).
