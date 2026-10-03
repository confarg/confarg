# A whole value followed by a subkey opens rather than collides

`--<field> <scalar> --<field>.<sub> <v>` used to let Python's own `TypeError` out of
`_set_nested` — the merge core cannot subscript a string. What the pair should *mean* is not
one question but three, because the parse is type-guided and the scalar means something
different at each field:

| The scalar at that field | Example | Was |
|---|---|---|
| provably meaningless | `dict[str, str] \| None`, a dataclass | already headed for a build error on its own |
| a legitimate value | `dict[str, str] \| str` | builds fine on its own |
| a documented shorthand | `Callable[…]` | `"pkg.func"` ≡ `{fn: "pkg.func"}` |

The rule chosen: **open the scalar into whatever it means to its field, then let the subkey
refine it**; where it means nothing, the subkey replaces it. Only `Callable` has such a
meaning today, so only it is promoted, and `promote_bare_spec` writes that equivalence down
once. The alternatives, and why not:

- **One blanket rule, "the subkey replaces the scalar."** Smallest possible change — a single
  branch in the type-blind `_set_nested` — and it matches the adapters and `_deep_merge`
  exactly. Rejected because it discards a value the user meaningfully typed, and the callable
  case then fails with *must specify one of 'fn', 'class', or 'call'*: an error that says the
  user named no target when they named one two tokens earlier.
- **One blanket rule, "raise a `ConfargError`."** Never silent. Rejected because vanilla would
  then refuse a pair the four adapters and the file-then-CLI path keep accepting, which is a
  new unapproved parity gap, not a fix; making *those* raise instead is a much larger change
  reaching into `_deep_merge`, and pushes a type-shaped judgement into the layer whose
  contract is that it does not make them ([pipeline](../pipeline/merge-build-contract.md#merge-build-contract)).
- **Split by whether the scalar was meaningful** — replace for a dict field, raise for
  `dict | str` and for `Callable`. The most conservative reading: nothing meaningful is ever
  dropped and no spelling is invented. Rejected because it gives one syntax two outcomes
  decided by the field's type, which is hard to document and harder to predict, and it refuses
  the callable pair rather than doing the obvious thing with it.

Cost: at a union like `dict[str, str] | str`, where a scalar *is* legitimate but is not a
shorthand for anything, the subkey still discards it silently. That is the same last-write-wins
the other three cells of the table already had, and the reverse argv order discards the subkeys
just as quietly ([pipeline](../pipeline/deep-merge.md#scalar-intermediates)).

Making this reach the adapters is what kept it from being a vanilla-only fix: the argv scan
that discovers bind parameters already reads a callable named by an opener flag, a `{…}` blob
or a config file, so the bare string became a fourth source feeding the same type-guided walk
rather than a new mechanism ([CLI adapters](../cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags)).
