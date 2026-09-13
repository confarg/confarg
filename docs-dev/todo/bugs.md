# Bugs

Defects, unapproved divergences between front-ends or channels, and code that deviates from
the documented intent. See [README.md](README.md) for the ticket format.

## Parity gaps

Cross-channel parity is mandatory (CLAUDE.md); every entry here is a violation nobody has
approved, not a design choice.

### BUG-2 — Adapters cannot set a scalar root from the CLI

**Where:** `src/confarg/cli/` · **Filed:** 2026-09-12
**Effort:** L · **Risk:** medium

A non-struct target is set from argv as `--<cli_prefix> VALUE`, but `cli_prefix` is
vanilla-only, so the adapters have no spelling for it. Environment variables and config files
set a scalar root in every front-end; the CLI does not.
See [03-cli-parsing.md#cli_prefix](../architecture/03-cli-parsing.md#cli_prefix).

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

### BUG-8 — A bare struct flag with no value is vanilla-only

**Where:** `src/confarg/cli/argparse/_spec.py` (`FlagSpec.nargs`) · **Filed:** 2026-09-13
**Effort:** M · **Risk:** low

`--<structfield>` with no value means "use defaults" in vanilla
([03-cli-parsing.md#token-consumption](../architecture/03-cli-parsing.md#token-consumption))
and merges nothing; the adapters register the flag with `nargs=None` and their framework
demands a value. `FlagSpec.nargs` has no `"?"`, and click cannot express an optional-value
option at all, so closing this needs a decision on the vocabulary — or on retiring the
no-value form, which contributes nothing to the merged dict.
See [04-cli-adapters.md#whole-value-flags](../architecture/04-cli-adapters.md#whole-value-flags).

### BUG-9 — `dict | None` does not accept the whole-mapping token that `dict` does

**Where:** `src/confarg/_parse_cli.py` (`_accepts_object_value`) · **Filed:** 2026-09-13
**Effort:** S · **Risk:** medium

`--env '{"a": "b"}'` decodes for `dict[str, str]` and for `Sub | None` (the union arm tests
`_is_dc` on each variant), but not for `dict[str, str] | None`: `_is_dict` is false on the
union and no arm tests dicts. The token is stored raw and `build()` then rejects it. This is
a channel-wide inconsistency in vanilla, not an adapter gap — the adapters mirror it
deliberately so their merged dict stays byte-identical. The fix is one arm in
`_accepts_object_value`, but it changes vanilla's parse result, so it needs its own decision.

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

### BUG-12 — `_UnionSeqToken` leaks into dumps

**Where:** `src/confarg/_serialize.py` (`_serialize_leaf`) · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low

Tokens must never leak into dumps
([09-invariants.md#tokens-mean-untyped-text](../architecture/09-invariants.md#tokens-mean-untyped-text)),
but the unwrap tests `type(v) is _StrToken`, and `_UnionSeqToken` is a *subclass*:
`dump_file(merge(B, argv=["--input", "hello"]), "c.yaml")` for `input: bool | list[str]`
raises `RepresenterError: ('cannot represent an object', 'hello')` — a str subclass that YAML
will not represent, while JSON happily writes it as a string. The exact-type test is a
deliberate choice ("so other `str` subclasses are untouched",
[05-types-and-construction.md#token-model](../architecture/05-types-and-construction.md#token-model)),
so widening it to `isinstance` is a decision, not a typo fix: it also flattens a user's own
`str` subclass. The alternative is to name confarg's own token types explicitly.

### BUG-13 — A force-cast cannot be dumped, though the file spelling exists

**Where:** `src/confarg/_serialize.py` (`_serialize_untyped`) · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low

`--count.int 5` stores `_Pinned(tp=int, value='5')` in the merged dict (`_cast.resolve_forced_value`),
and no writer accepts a `_Pinned`: `dump_file` raises in YAML, JSON and TOML alike. Unlike the
coerced leaves of BUG-10 this one loses nothing when written, because the cast already has an
exact file spelling — `{"__cast__": "int", "__value__": "5"}`, read back by
`_construct._try_pinned_dict` — so `_serialize_untyped` can emit that dict and the pin
survives the round trip intact. Only the untyped path is affected; a `_Pinned` never reaches
`dump(instance)`, which serializes a constructed object.
See [05-types-and-construction.md#cast-pinning-in-files](../architecture/05-types-and-construction.md#cast-pinning-in-files).

### BUG-14 — `_needs_tag` counts a registered leaf as a struct variant

**Where:** `src/confarg/_serialize.py` (`_needs_tag`) · **Filed:** 2026-09-13 ·
*(inferred — from code reading; currently unreachable, no test covers it)*
**Effort:** S · **Risk:** low

`_needs_tag` builds `struct_vars` with `_is_struct`, which is `True` for a registered leaf
type that happens to have an `__init__` (`UUID` does). In a union of one struct and one such
leaf it therefore sees two struct variants and hands the leaf to `_disambiguate_struct` as a
candidate, which can tag — or refuse to tag — the wrong way. Unreachable today because
`_serialize_by_type` now routes a registered leaf to `_serialize_leaf`, so `serialized` is a
scalar and the `isinstance(serialized, dict)` guard fires first; the filter should still use
the same registry exclusion as the dispatch
([05-types-and-construction.md#leaf-coercion](../architecture/05-types-and-construction.md#leaf-coercion)).
