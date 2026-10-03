# Safety model

Expressions come from config files, env and argv, so they are evaluated by a small
interpreter over a whitelisted AST, never `eval`:

- allowed nodes: constants, names, attributes, integer subscripts, arithmetic, comparisons,
  boolean ops, conditional expressions, calls (`_ALLOWED_NODES`);
- calls only to whitelisted free functions (`abs min max round ceil floor str int float bool
  len`) and string methods (`upper lower strip split replace startswith endswith join`); no
  indirect calls;
- no attribute starting with `__`;
- consequently no literals for lists/dicts/sets, no slices, no comprehensions, no lambdas, no
  f-strings; the `${...}` regex also forbids `}` inside an expression.

`a.b` is first tried as a config path; only if that fails is it a real attribute access
(e.g. the receiver of a string method), and a miss is reported as a missing field rather
than an `AttributeError` on `dict`.
