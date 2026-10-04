# List syntax divergence

List values are space-separated for vanilla/argparse (`--tags a b`), repeated flags for click
and typer (`--tags a --tags b`), either for cyclopts. This is an approved divergence imposed by
click and inherited by typer's fork of it; tests keep it visible
([testing](../testing.md#list-syntax-split)). The append/delete
ordering on top is shared. The first item of a space-separated run may carry the `=` spelling
(`--tags=a b` is `['a', 'b']`) on vanilla and cyclopts; argparse's `=` binds the one token after
it and its parser exits on the rest, the approved divergence BUG-75 recorded
([whole-value flags](whole-value-flags.md#whole-value-flags)).

What the approval covers is the **spelling** — which of the two forms a framework accepts — and
not what a repeated flag *means*. The two once came apart unnoticed: `--tags a --tags b` built
`['a', 'b']` under click, typer and cyclopts and `['b']` under vanilla and argparse, with no
diagnostic either way, so the repeated line the click and typer tutorials teach lost every value
but the last when it was pasted into a vanilla app. That was an unapproved gap rather than a second
divergence, and it resolved towards **accumulation** (BUG-37): last-wins is unreachable for the
clicklike front-ends — repetition being their only multi-token spelling, taking just the final
occurrence would leave a click user no way to write `['a', 'b']` at all. So `--f x --f y` is a
second spelling of `--f x y` in all five front-ends, and mixing the two spellings adds up
(`--f x y --f z` → `['x', 'y', 'z']` wherever both are accepted).

The rule holds for the multi-token **field** flags: a varlen collection, and a union with a
sequence variant (`int | list[int]`, `str | tuple[str, str]` — the clicklike front-ends already
accumulated on both). It stops at a fixed-arity flag on its *plain* spelling (`tuple[X, Y]`,
namedtuple), which takes one value and is last-wins on repetition everywhere — under `Optional`
the resolved type is a union with a sequence variant, so the flag belongs to the family above and
accumulates, its arity deferred to `build()` (BUG-79;
[design decisions](../design-decisions/namedtuple-is-a-fixed-length-sequence.md#a-namedtuple-is-a-fixed-length-sequence)) — and it is not the `+`
suffix, which is a merge operator rather than a spelling (below).

The config flag is not a field flag and crosses the same seam: its space-separated multi-file
run declines on the two clicklike front-ends, an approved divergence of its own recorded in
[config file flags](../cli-parsing/config-file-flags.md#config-file-flags) (BUG-99).

Two consequences follow from the accumulation being over **tokens**, not over shaped values:

- vanilla joins the occurrences and shapes the result once, in `_parse_cli._varlen_value` /
  `_union_seq_value`. A whole-value inline JSON array is therefore a *single-token* spelling
  (`_lone_json_array`): `--tags '["a","b"]'` decodes, while `--tags '["a","b"]' --tags '["c"]'`
  and `--tags '["a","b"]' z` are two ordinary items, on the adapters too, whose CLI channel is
  the same loop ([argv is the only writer](model.md#argv-is-the-only-writer)).
- argparse keeps only the last occurrence under its plain store, and confarg does not shape
  that: the parse result's values are never read, so a rule over them would be a second writer
  over the parse result ([argv is the only writer](model.md#argv-is-the-only-writer)). A
  spec's `action="extend"` (`FlagSpec.accumulates`, BUG-37) once kept the Namespace an honest
  picture of what was typed; it was dropped because the merge needs no such promise, and a host
  reading the Namespace itself now sees argparse's own last-wins, not the accumulation the
  merge builds. `default=argparse.SUPPRESS` still keeps a flag nobody typed off the Namespace,
  and a first occurrence with no token still yields `[]`. click and typer accumulate through
  `multiple=True`, cyclopts through `consume_multiple` — the frameworks' own mechanisms for
  their repetition spelling, not a confarg rule over their results.

Neither axis is the `+` suffix, which names the merge axis instead and is shared by all three
channels ([design decisions](../design-decisions/plus-is-a-merge-operator.md#the--suffix-is-a-merge-operator-not-a-list-spelling)).
