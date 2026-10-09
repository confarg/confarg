# Look-alike code that behaves differently stays apart

A collapse is worth making when the copies are the same code: one loop written three times
(`_construct._first_constructible`), one filter spelled four ways (`_callable._fillable_params`).
It is declined when the copies only share a *shape*, and the one function replacing them would
have to take every difference between them as a parameter. The differences are then still all
there, but they move out of the code, where a reader sees them, into a table or a flag, where a
reader has to work them out. Two collapses were declined on that ground when REF-52 closed:

- **The four scalar coercions in `typedload/_coerce.py`** (`_coerce_bool_value`,
  `_coerce_int_value`, `_coerce_float_value`, `_coerce_str_value`) all pass a native value
  through, parse a token and refuse anything else. But `bool` refuses a bad token with its own
  message, which lists the accepted words; `int` passes an `int` through but refuses a `bool`;
  `float` refuses an `int`; and `str` parses *any* string, not only a token, so a `StrEnum` member
  becomes its plain value. Driving all four from `_SCALAR_COERCIONS` would need each entry to
  carry what it passes through, what it parses and how, and a special case for `bool`, which is
  four functions' worth of rules spread across a table, saving about ten lines.
- **`dictexpr`'s `_strip_anchor` and `_name_anchor`** already share their one common step,
  `_replace_spans`, run over `_anchor_markers`. What is left differs: one drops the root
  markers a name follows, the other names every marker and has to pick a stand-in spelling the
  body does not use. Folding them further saves two lines. The other duplication in `dictexpr`,
  between `_resolve_single` and `_map_expressions`, was a real one and did collapse: the two
  loops differed only in what a span became, so `_rewrite_spans` writes the accumulate loop and
  a `Callable[[_ExpressionSpan], str]` carries each caller's answer, escape handling included
  (REF-54).

The precedent is Sandi Metz's "duplication is far cheaper than the wrong abstraction", as
applied in Kent C. Dodds's "AHA programming": an abstraction that needs a parameter for each
of its callers' differences is the wrong one. The cost is that a change to what the four
coercions do share, such as a new way of refusing a value, has to be made four times.
