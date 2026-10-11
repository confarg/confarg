# cli_prefix

`cli_prefix` requires `--<prefix>.` on every flag, so configuration arguments stay
distinguishable from the host application's own — the case the adapters exist for. All four
front-ends support it ([CLI adapters](../cli-adapters/cli-prefix-boundaries.md#the-cli_prefix-boundaries)).

The adapters take it on `populate_*`, which owns flag naming, and **record** it there; the
merge step recovers it, so `merge_*`/`from_*` need not repeat it. Passing one that disagrees
with what was registered raises rather than silently matching no flag — the objection that
once kept the prefix out of the adapters, answered instead of avoided.

Vanilla owns the whole command line, so a flag outside the prefix is an
`UnknownArgumentError`. An adapter does not: there, a flag outside the prefix belongs to the
host framework and is left alone. That is not a divergence in the prefix but the adapter
model itself — it holds with or without one.

A non-struct (scalar) target has no field name to address, so `--<prefix> VALUE` is its only
CLI spelling, handled by `_handle_scalar_root`, on the adapters too. Without a prefix it has no CLI spelling at all, in any front-end.
`--<prefix>.json` reaches the same root through the
[root cast](casts-and-reserved-words.md#force-casts).

A **struct-like** root (dataclass, plain class — a registered leaf included) refuses the bare
flag instead (BUG-91): nothing about `--<prefix> VALUE` names a field, and a value consumed
for the empty path would be silently dropped — the adapters had refused it at parse time all
along, so vanilla's `UnknownArgumentError` is the refusal the five front-ends share. A
registered leaf as the root keeps its flat tagged spelling
(`--<prefix>.class uuid.UUID --<prefix>.hex …`), the one
[a registered leaf is opted back in with](../design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in).

## A non-struct root is set whole

`build()` reads a non-struct root from `__root__` alone, so no flag addresses a path below it
(BUG-172): `--app.0.size` on a `list[Item]` root, `--app.k` on a dict root, `--app.x` on a
namedtuple root and the tag `--app.class` on an `int` root are all `UnknownArgumentError`.
Vanilla had written each at the top of the merged dict, beside `__root__`, where the value was
dropped without a word. The adapters refused the element flags they never registered, and
accepted the ones the walk let them register. Such a root is spelled whole: the bare
`--<prefix>` or the [root cast](casts-and-reserved-words.md#force-casts) `--<prefix>.json`,
and a missing field below it names that cast as its remedy
([construction](../types/construction.md#a-missing-fields-remedy-is-spelled-as-the-cli-spells-it)).

One decision-maker settles it: `_walk_target`, which every dotted path is resolved against —
vanilla's loop, the adapters' patch-flag registration, the host-mode skip, the mount check and
the environment, whose variables it reaches as a flag's path
([environment parsing](../environment-parsing.md#environment-parsing), BUG-115).
For a non-struct root it is the [locals graft](../locals.md#walk-target-graft) alone, so the
namespace beside the root value stays addressable (`--app.locals.n`), and nothing else does.
Four consequences follow from that one answer:

- A dict root's `--<prefix>.json` (and `--json` without a prefix, and `<PREFIX>JSON`) is the
  root cast, not a key named `json`: no key of that dict is a CLI member, so the
  [real field wins](casts-and-reserved-words.md#real-field-wins) rule has nothing to yield to.
- A config file mounted below the root (`--app.config.0`, `APP_CONFIG__0`) is refused with
  the error that says so. A root config file writes the value under `__root__` instead.
- With no prefix, an adapter's host owns every dotted flag on such a root, locals aside,
  since the host-mode skip asks the same walk.
- Only the bare `<PREFIX>` and `<PREFIX>JSON` set the root from the environment; any other
  variable under the prefix is warned about and ignored, as an unknown field of a struct root
  is, since the environment warns where the CLI refuses.

Writing the path under `__root__` as a patch was rejected. It is a feature, not a fix: the
four adapters would have to register element flags of a collection root, and the environment
would need `APP_0__SIZE` for parity, the opposite of the direction BUG-115 took for it. A list
root without a prefix would still have no spelling, since `--0.size` reads as a positional.
Hydra wants a mapping as its primary config, and pydantic-settings and simple_parsing want a
model or a dataclass at the root. tyro is the exception: it registers `--0.x` below a tuple of
dataclasses.
