# Bugs

Defects, unapproved divergences between front-ends or channels, and code that deviates from
the documented intent. See [README.md](README.md) for the ticket format.

## Parity gaps

Cross-channel parity is mandatory
([09-invariants.md#cross-channel-parity](../architecture/09-invariants.md#cross-channel-parity));
every entry here is a violation nobody has approved, not a design choice.

### BUG-3 — A root-level JSON cast is refused in the environment

**Where:** `src/confarg/_parse_env.py` (`_apply_env_json_cast`) · **Filed:** 2026-09-12 ·
*(inferred — from code reading, no test covers it)*
**Effort:** M · **Risk:** high

CLI `--json '{…}'` injects a whole configuration, but `<PREFIX>JSON` is declined at the root
and then reported as an unknown field. Confirm with a test first: if it reproduces, the fix
belongs in the canonical cast path rather than a second special case in `_parse_env`.

### BUG-6 — Subclass flags are registered only for subclasses already imported

**Where:** `src/confarg/cli/argparse/_build.py` (`tp.__subclasses__()`) · **Filed:** 2026-09-12 ·
*(inferred — from code reading, no test covers it)*
**Effort:** L · **Risk:** medium

Flag registration for a base-class field enumerates `__subclasses__()` at parser-build time, so
a subclass that has not been imported yet contributes no flags. Since unknown CLI flags are
errors, `--f.class=pkg.Sub --f.only_in_sub=1` would fail where the same keys in a file succeed —
`build()` imports the tagged class itself. The same import dependence is why subclass inference
was rejected ([10-design-decisions.md#no-implicit-subclass-inference](../architecture/10-design-decisions.md#no-implicit-subclass-inference));
here it leaks into the CLI channel. Confirm with a test first.
See [04-cli-adapters.md#union-inheritance-and-cast-flags](../architecture/04-cli-adapters.md#union-inheritance-and-cast-flags).

### BUG-16 — A NamedTuple takes a whole `{...}` token in the environment but not on the CLI

**Where:** `src/confarg/_parse_cli.py` (`_accepts_object_value`) · **Filed:** 2026-09-14
**Effort:** S · **Risk:** medium

`MYAPP_NT='{"a": 5}'` builds `NT(a=5, b=2)`; `--nt '{"a": 5}'` stores the token raw and
`build()` fails with `Cannot construct NT at 'nt': expected list, tuple, or dict, got
_StrToken`. `_parse_env` tests `_is_namedtuple` in both its direct and its union arm;
`_accepts_object_value` tests `_is_dc`, which a NamedTuple is not, so neither `NT` nor
`NT | None` qualifies. Fixing it means adding the arm *and* checking it against the
fixed-tuple consumption path a NamedTuple field also has
([03-cli-parsing.md#token-consumption](../architecture/03-cli-parsing.md#token-consumption)),
which the `{`-prefix guard should keep out of the way.
See [10-design-decisions.md#optionality-does-not-change-what-a-whole-value-accepts](../architecture/10-design-decisions.md#optionality-does-not-change-what-a-whole-value-accepts).

### BUG-17 — `Callable | None` does not accept the whole-spec token that `Callable` does

**Where:** `src/confarg/_parse_cli.py` (`_accepts_object_value`),
`src/confarg/_parse_env.py` (`_store_env_value`) · **Filed:** 2026-09-14
**Effort:** S · **Risk:** medium

`--fn '{"class": "pkg.Greeter", …}'` decodes into a callable spec, but the same token on a
`Callable[[str], str] | None` field is kept raw in both channels and reaches the importer as
a symbol name: `SymbolImportError: Cannot import '{"class": …}': no importable module found
in path`. Same shape as the dict case, and the rule is already recorded — optionality is not
a statement about syntax — so this is applying it, not deciding it. Both channels move
together, as they did there: the callable arms are `_is_callable` in
`_accepts_object_value` and in `_parse_env._store_env_value`'s `accepts_obj`, and neither
union arm asks about callables. Watch the spec/bind merge in `cli/_collect.py`
(`_whole_value` → `_merge_blob_into_spec`), which the raw path never reaches today.
See [10-design-decisions.md#optionality-does-not-change-what-a-whole-value-accepts](../architecture/10-design-decisions.md#optionality-does-not-change-what-a-whole-value-accepts).

## Intent versus implementation

### BUG-4 — Stealing order does not match the documented rule

**Where:** `src/confarg/typedload/_coerce.py` (`_steal_order`) · **Filed:** 2026-09-12
**Effort:** M · **Risk:** high

Intended (confirmed by the maintainer, and what the tutorial in `examples/7_stealing_rule/`
teaches): `registered leaf > Enum > [float, int, bool, None] > str`. Implemented:
`Enum > other non-str types in declaration order > str`, with `None` and bool-vs-int handled
first. Fix the code, not the tutorial.
See [05-types-and-construction.md#stealing-rule](../architecture/05-types-and-construction.md#stealing-rule).

### BUG-7 — Typer integration is claimed, never tested, and currently broken

**Where:** `src/confarg/cli/click/_register.py`, `tests/cli/click/` · **Filed:** 2026-09-12
**Effort:** L *(XL if typer becomes a supported front-end)* · **Risk:** medium

`README.md` and `docs/index.md` both promise confarg "can integrate with your favorite argument
parser library such as `argparse`, `click`, `typer` or `cyclopts`". Nothing verifies the typer
half: `typer` is in the `dev` dependency group (`pyproject.toml:37`) but no test, example or
module imports it, and the four front-ends behind the `loader` fixture are argparse, click,
cyclopts and vanilla only.

Probed, and it does not work. Registration is fine — `populate_command(Config,
typer.main.get_command(app), ...)` on a `TyperCommand` registers every expected option,
subkeys included — but invocation dies in `click.core.Parameter.handle_parse_result` with
`AttributeError: 'Context' object has no attribute '_param_default_explicit'`, because typer
supplies its own `Context` from its vendored click shim while the adapter registers real
`click.Option` instances. Isolated from confarg: appending a bare `click.Option` to a typer
command reproduces it identically (typer 0.27.2, click 8.5.0), so the fix direction is a seam
letting the option class be `typer.core.TyperOption` when the command is a typer command,
rather than anything in the merge path.

Decide the scope first, since it sets the parity obligation: if typer is a supported
front-end it needs the shared `loader`-fixture contract like the other three
([12-testing.md](../architecture/12-testing.md)); if it is merely "click underneath, at your
own risk", the two documentation claims must say so. Either way the claim and the test suite
have to agree.
See [04-cli-adapters.md](../architecture/04-cli-adapters.md).

### BUG-13 — A force-cast cannot be dumped, though the file spelling exists

**Where:** `src/confarg/_serialize.py` (`_serialize_untyped`) · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low

`--count.int 5` stores `_Pinned(tp=int, value='5')` in the merged dict (`_cast.resolve_forced_value`),
and no writer accepts a `_Pinned`: `dump_file` raises in YAML, JSON and TOML alike. Emit the
file spelling of the cast instead — `{"__cast__": "int", "__value__": "5"}`, read back by
`_construct._try_pinned_dict` — unwrapping the `_StrToken` in `__value__` so it does not trip
BUG-12. A `__cast__` dict that came from a file already re-dumps unchanged, so the emission is
idempotent.

Writing the *coerced* value instead, as BUG-10 does for a coerced leaf, is tempting and wrong.
It is sufficient while the pin only separates scalars — a file is self-describing and its values
are never re-interpreted, so `int | str` and `str | int` both read `5` back as an `int`. It is
lossy as soon as a non-scalar leaf variant precedes the scalar: `Color | str` reads `v = "FOO"`
back as `Color.FOO` and `Path | str` reads `v = "x/y"` back as a `Path`, by declaration order.
`--v.str FOO` builds `'FOO'` and a plain `v = "FOO"` dump does not, which breaks
`build(merge()) == build(merge(dumped))`
([10](../architecture/10-design-decisions.md#dump-round-trips-at-the-built-object)).
`_serialize_untyped` is type-blind and cannot tell the two apart, so it must keep the pin.
Only the untyped path is affected; a `_Pinned` never reaches `dump(instance)`, which serializes
a constructed object — the typed path has its own version of this, BUG-15.
See [05-types-and-construction.md#cast-pinning-in-files](../architecture/05-types-and-construction.md#cast-pinning-in-files).

### BUG-15 — `dump()` drops a leaf a union variant will steal back

**Where:** `src/confarg/_serialize.py` (`_serialize_union`) · **Filed:** 2026-09-13
**Effort:** L · **Risk:** medium

`dump(E(v="FOO"))` for `v: Color | str` emits `{'v': 'FOO'}`, and loading that file back builds
`Color.FOO`: `load(dump(x)) != x`, the one round trip
[01-pipeline-and-contracts.md#public-api-seams](../architecture/01-pipeline-and-contracts.md#public-api-seams)
does promise. Same for `Path | str` holding a plain `str`. Native file values are matched in
declaration order, so any `Enum`, `Literal`, registered leaf or type-ref variant ahead of the
scalar steals the bare scalar on the way back in. No `_Pinned` is involved — this is the typed
sibling of BUG-13, and unlike `_serialize_untyped` the typed path knows the declared type and
can decide. Fix direction: a `_needs_cast` check on leaf variants mirroring `_needs_tag` on
struct variants — emit `{__cast__, __value__}` only when re-reading the bare scalar would not
select the variant that produced it. Precedent: YAML emitters tag a scalar (`!!str 5`) exactly
when the plain form would resolve to another type. It changes `dump()` output, so it needs a
decision recorded in [10-design-decisions.md](../architecture/10-design-decisions.md).
See [05-types-and-construction.md#serialization](../architecture/05-types-and-construction.md#serialization).

### BUG-16 — Three struct checks still ignore the leaf registry

**Where:** `src/confarg/typedload/_construct.py` (lines 359, 607/617, 872) · **Filed:** 2026-09-14
**Effort:** S · **Risk:** medium

`_is_struct_variant` is the canonical "does this type get taken apart into fields?"
([09-invariants.md#delegate-to-the-canonical-function](../architecture/09-invariants.md#delegate-to-the-canonical-function)),
but three sites still ask bare `_is_struct`, so a registered leaf with an all-default
`__init__` is still a struct to them. Two are observed with `UUID` registered:

- **line 359** — a *missing* required field typed as a registered leaf takes the
  "struct with all-default fields is built from `{}`" branch: `build(C, {})` for `id: UUID`
  escapes as a raw `TypeError: one of the hex, bytes, ... must be given` instead of
  `MissingFieldError`. A stdlib exception leaking out of `build()` is the worst of it.
- **lines 607/617** — `_construct_union_by_tag` accepts a tag naming the leaf and takes it
  apart: `{"class": "uuid.UUID", "int": 5}` builds `UUID(int=5)` from fields, which is exactly
  what registration says never happens
  ([10-design-decisions.md#a-registered-leaf-is-never-a-struct-variant](../architecture/10-design-decisions.md#a-registered-leaf-is-never-a-struct-variant)).
- **line 872** — `_value_matches_type` routes a registered leaf to `_struct_matches_value`,
  so a dict can "match" a leaf-typed field. *(inferred — no test reaches it now that both
  `_disambiguate_struct` call sites filter the registry out first.)*

Found while closing BUG-14, which fixed the same mistake at the dispatchers and the two
union-variant filters; these three were left out of that change deliberately, not missed.
Line 607 is a behavior decision, not a typo — say whether a tag may name a leaf at all — so it
wants a note in [10-design-decisions.md](../architecture/10-design-decisions.md) either way.
