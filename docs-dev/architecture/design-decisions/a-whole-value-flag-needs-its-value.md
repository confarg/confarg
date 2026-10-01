# A whole-value flag needs its value

`--db` with nothing after it is an error in every front-end, exactly like `--port` with
nothing after it. Vanilla used to make one exception: a **non-optional dataclass** field
consumed no token and merged nothing. The exception was
indefensible on three counts.

- It bought nothing. The branch returned without calling `_set_nested`, so the flag was a
  silent no-op — and not "use defaults" as its comment claimed, since a value already merged
  from a config file stayed put.
- It was inconsistent inside vanilla. The guard tested `_is_dc(ft)` on the resolved-but-not
  Optional-unwrapped type, so `Sub | None` and `dict[str, str]` — which get the same bare
  whole-value flag — already raised `Missing value`. Only one of the four whole-value shapes
  had the exception.
- No adapter could reproduce it, and one of them never can. argparse has `nargs="?"` and
  click reaches the same shape with `is_flag=False, flag_value=<sentinel>`, but cyclopts
  fixes a parameter's token count by construction: annotating the optional-value shape fails
  with `Cannot Union types that consume different numbers of tokens`. Nor can an adapter
  rewrite argv around the gap — the user owns the framework's parse call, not confarg.

Teaching three front-ends a form that contributes nothing to the merged dict, on a field
shape the fourth already refused, was the worse trade. The rule is now uniform, so
`_accepts_object_value` decides *what* a whole-value flag decodes and nothing decides
*whether* it needs one.

A **fixed arity** is the same rule counted: `--pair` on a `tuple[int, int]` needs both of its
tokens, and a short run is `Missing value for '--pair'` rather than a one-element tuple. An
optional *element* does not soften it — `tuple[str, int | None]` still needs two tokens — for
the reason the paragraphs above give: click and typer register the exact count and already
refuse the short form outright, so tolerating it in vanilla was a divergence nothing could
reproduce. Filling the optional slot is spelled rather than inferred from where argv stopped,
and all three spellings survive: `--pair '["hello"]'`, `--pair hello null`, and a config file's
`pair: [hello]`. Arity is still `build()`'s to judge once the tokens are in hand:
`--pair '[13]'` is an *arity* error, not a missing value, because the whole-value token is one
value that happens to be short, and the parser can only prove a token missing when argv is what
ran out. The adapters' CLI channel is the same loop over the same argv
([CLI adapters](../cli-adapters/whole-value-flags.md#whole-value-flags)), so the rule is one
rule on every front-end (BUG-58).

The upper bound is the same decision read from the other end, and it lands on the *scan* rather
than on the field: `--pair 1 2 3` does not grow the tuple, because vanilla stops consuming at
the declared count and then meets `3` as a bare word in argv. So the surplus is reported as
`Unexpected positional argument: '3'` — the argv-level diagnosis that names the offending
token — and not as an arity error naming the flag, which is what `build()` would have said had
the over-long list reached it. Keeping the flag out of the message is the point: the pair was
filled, and what is wrong is the word after it (BUG-60).
