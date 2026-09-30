# Config file flags

`--<config_flag>[.subpath][+] FILE…` is intercepted **before** field lookup, so a field with
the same name as `config_flag` could never be set; that shadowing is rejected up front by
`_check_reserved_key_conflict`, the one canonical shadow check for reserved top-level
names. `_addresses_key` is the one canonical test for "this token belongs to a reserved
namespace", shared by the config flag and the locals namespace across CLI and env.

`_collect_config_file_pairs` is a lenient re-scan used by the adapters to recover argv
order after the framework already consumed the paths; it never raises.

The first path may carry the `=` spelling (`--config=a.yaml b.yaml` reads both) on vanilla and
cyclopts; argparse's `=` binds the one path after it and its parser exits on the rest, the
approved divergence BUG-75 recorded
([whole-value flags](../cli-adapters/whole-value-flags.md#whole-value-flags)).
