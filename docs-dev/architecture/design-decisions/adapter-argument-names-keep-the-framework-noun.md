# Adapter argument names keep the framework's noun

The second positional argument of each adapter names the object the user already holds: `merge_namespace(target, ns)` for argparse, `merge_context(target, ctx)` for click and typer, `merge_app(target, app)` for cyclopts, and `populate_parser(target, parser)`, `populate_command(target, command)`, `populate_app(target, app)` for registration.
A review (REF-9) asked whether one name, such as `cli`, should replace them all.

The framework's own vocabulary wins.
Each name is the one its framework's documentation uses, so a reader who has the framework open recognises the argument at the call site.
Precedents were not surveyed for this decision (*(inferred)* from the adapters' own naming).

The cost is that the five spellings differ, so a helper that is generic over the adapters must take the argument by position, not by name.
Nothing in the library does that today, and the parity tests call every adapter through the same `loader` fixtures, so the difference does not reach users.

Rejected: a single `cli` name.
It would make the signatures uniform, but every adapter call site would change, and `cli` is less informative than `ctx` or `app` to a reader who knows the framework.

The keyword set of `populate_*` is covered by the same review: `cli_prefix` defaults to `None`, as in [MergeOptions](../pipeline/api-seams.md#one-option-set) (see [cli-prefix](../cli-parsing/cli-prefix.md#cli_prefix)).
