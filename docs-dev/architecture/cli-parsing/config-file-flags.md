# Config file flags

`--<config_flag>[.subpath][+] FILE…` is intercepted **before** field lookup, so a field with
the same name as `config_flag` could never be set; that shadowing is rejected up front by
`_check_reserved_key_conflict`, the one canonical shadow check for reserved top-level
names. `_addresses_key` is the one canonical test for "this token belongs to a reserved
namespace", shared by the config flag and the locals namespace across CLI and env.

The adapters read `--config` files off argv with vanilla's loop, in command order
([CLI adapters](../cli-adapters/model.md#argv-is-the-only-writer)). `_collect_config_file_pairs`
is the cyclopts pre-parse refusal of a bare occurrence, which cyclopts would otherwise read as
an implicit value and assert on.

The first path may carry the `=` spelling (`--config=a.yaml b.yaml` reads both) on vanilla and
cyclopts; argparse's `=` binds the one path after it and its parser exits on the rest, the
approved divergence BUG-75 recorded
([whole-value flags](../cli-adapters/whole-value-flags.md#whole-value-flags)).

The multi-file run is spelled space-separated on vanilla, argparse and cyclopts
(`--config a.yaml b.yaml`) and by repetition on click and typer — an **approved divergence**
narrowed to the two clicklike front-ends (BUG-99, closed): a click `Option` cannot vary its
token count, so the flag registers `multiple=True`, which binds exactly one path per occurrence
and lets the framework's parser exit on the tokens that would complete a space-separated run,
before any confarg code runs. It is the config flag's half of the
[list syntax divergence](../cli-adapters/list-syntax-divergence.md#list-syntax-divergence), which
scopes its own approval to the multi-token *field* flags and leaves this one here; the
`--<config_flag>.<subpath>` scoped flags and the locals flag register the same `nargs="*"`
and decline the same way. Repetition is the spelling the two frameworks teach their own
users, the lean
[design decisions](../design-decisions/divergence-leans-to-the-backend.md#a-divergence-leans-towards-the-affected-backends-own-idiom)
settles, and the contract suite pins the decline beside the BUG-75 tests
([testing](../testing.md#list-syntax-split)).
