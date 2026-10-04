# A namedtuple is a fixed-length sequence

A namedtuple field takes every CLI spelling a same-arity `tuple` takes, and the whole `{...}`
object its field names additionally make meaningful. Vanilla used to treat it as a scalar: it
consumed one token, so `--pair 13 42` was `Unexpected positional argument: '42'`, `--pair
'[13, 42]'` and `--pair '{"x": 13}'` were stored as raw text and died in `build()`, and the
four adapters — which have registered the arity flag and the per-field flags all along —
disagreed with vanilla on a field shape they all support.

The fix is one classification, not three special cases. A namedtuple *is* a tuple subclass of
known arity, so:

- `_types._is_seq_variant` counts it as sequence-shaped, which is what
  `_union_has_seq_variant` and `_union_has_scalar_variant` are built from — so `Point | None`
  consumes its arity exactly as `tuple[int, int] | None` does, and optionality stays a
  statement about being unset rather than about syntax
  ([optionality does not change what a whole value accepts](optionality-and-whole-values.md#optionality-does-not-change-what-a-whole-value-accepts));
- `_types._fixed_seq_types` answers "how many positional tokens, of which types?" for both
  spellings, so the parser's collection test and its consumption branch cannot learn about
  namedtuples separately and drift apart;
- `_parse_cli._accepts_object_value` gains the namedtuple arm the env channel's `accepts_obj`
  has had all along, in both its direct and its union half — which is the parity gap the
  ticket was actually filed for.

The rejected alternative was to teach the whole-`{...}` arm alone, as the ticket proposed. It
closes the env/CLI gap the ticket names and leaves the larger one: vanilla would take a whole
object for a namedtuple but still refuse the positional form all four adapters accept. A
predicate that says "this field is sequence-shaped" cannot be right for `tuple[int, int]` and
wrong for a two-field namedtuple; splitting them is what produced the gap.

Precedent: `typing.NamedTuple` is documented as a tuple subclass, and every consumer here
already treated it as one *somewhere* — the env channel accepts both JSON shapes for it, the
adapters register its arity, `construct` builds it from a list. Vanilla's argv parser was the
only holdout.

- Follow-through: the classification had to reach `construct`'s union split too. A lone token
  on a multi-variant union with a namedtuple variant used to fail in the parser (`--v 3 4` was
  a stray positional on `str | Point`); it parses greedily like `str | tuple[int, int]` now, so
  the failure moved down to `_construct_union_leaf`, which still partitioned variants with
  `_is_tuple` and left the namedtuple among the *scalar* leaves. The split asks `_fixed_seq_types` instead, and so does
  the arity filter it feeds, so the one function that answers "fixed arity, of which types?"
  answers on the way in as well
  ([types](../types/leaf-coercion.md#leaf-coercion)).
- Follow-through: the identity reaches the negative index (BUG-80). `--pt.-1` counts from the
  end everywhere, as `--lang.-1` always did on the plain tuple: `build()` maps an index-keyed
  dict through `_indexed_dict_to_positions` — the fixed tuple's own resolver, one
  decision-maker for "a negative key counts from the end" — an integer key (a YAML file's own
  parsing of a bare `-1:`) is accepted alongside its string spelling, and the registration and
  the collector carry the third spelling beside the name and the index, the deep fields'
  spellings included. Every index spelling is hidden from `--help`
  ([index spellings are hidden from help](index-spellings-are-hidden-from-help.md#index-spellings-are-hidden-from-help));
  the odd spellings `-0` and `+N` still diverge across the front-ends (BUG-97, open).
- Boundary: taking a whole `{...}` or `[...]` token on a fixed-arity flag needs a framework
  that can vary a flag's token count at parse time. argparse and cyclopts can and now do;
  click cannot and declines, the approved divergence argued in
  [CLI adapters](../cli-adapters/whole-value-flags.md#whole-value-flags). That was never a namedtuple property —
  `tuple[int, int]` behaved identically — so it was filed once, for both (BUG-20, closed).

A note on the ID: `BUG-16` was used twice. The first one —
[an explicit tag opts a leaf back in](an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in) — closed long
before the namedtuple ticket was filed under the same number, against
[todo/README.md](../../todo/README.md)'s rule that IDs are never reused. Both are closed, and the
next free number on `bugs.md` is what the rule intends.
