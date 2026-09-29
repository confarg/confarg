# Optionality does not change what a whole value accepts

`--env '{"a": "b"}'` and `MYAPP_ENV='{"a": "b"}'` decode the same for `dict[str, str]` and for
`dict[str, str] | None`. Optionality says what a field may be *unset* to; it is not a statement
about its syntax, so making `| None` the difference between a decoded mapping and a raw string
would be a spelling trap. Both predicates —
`_parse_cli._accepts_object_value` and the `accepts_obj` test in `_parse_env._store_env_value` —
therefore ask their union arm about every type the bare arm accepts: structs, namedtuples,
dicts and callables. In `_accepts_object_value` that is literally one test, the inner
`accepts()`, applied to the type and then to each non-`None` union variant; nothing may answer
only for the bare arm.

Both channels were fixed in one change on purpose. The gap was symmetric, so repairing only the
CLI would have *created* a divergence where none existed, which
[invariants](../invariants.md#cross-channel-parity) forbids. Collections were already consistent under
this rule (`list[str] | None` takes a JSON array in the environment, and the CLI's
`_union_has_seq_variant` reaches it), so dicts were the outlier, not the precedent.

- Cost: a token that used to survive as a string now decodes, so a target with an
  `Any`-tolerant `| None` arm that was relying on the raw text sees a mapping instead. Nothing
  in the channel model ever promised that text; the raw value could not be built.
- Callables came second, the same way. `Callable[…]`
  had its own bare-arm-only test — `_is_callable` sat *beside* the union walk in
  `_accepts_object_value`, not inside it — so `Callable[…] | None` kept the spec token raw and
  handed the whole JSON blob to the importer, in both channels. Folding `_is_callable` into
  `accepts()` removed the second place a whole value could be decided, which is why the fix is
  one line smaller than the bug. The namedtuple half was settled separately, by making a
  namedtuple a sequence everywhere
  ([a namedtuple is a fixed-length sequence](namedtuple-is-a-fixed-length-sequence.md#a-namedtuple-is-a-fixed-length-sequence)).
- Decoding the blob was not yet registering the flags it implies: the adapters learned a
  callable's factory and `bind` flags from a `--<field>.class` opener on argv only, so a class
  named inside the blob left them unregistered, fixed the same way — by widening an
  existing walk, not by adding a scan. Vanilla, which re-reads argv, was
  never affected; the divergence was in the scan, not in this predicate, which is why it
  survived the fix above and needed its own.
