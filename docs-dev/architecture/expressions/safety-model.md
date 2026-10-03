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
  f-strings. A `}` inside a string literal is fine: delimiting is lexical, not a regex
  ([values and references](values-and-references.md#delimiting-an-expression)).

`a.b` is first tried as a config path; only if that fails is it a real attribute access
(e.g. the receiver of a string method), and a miss is reported as a missing field rather
than an `AttributeError` on `dict`.

## A function is named only by a call

A name is a whitelisted function only as the callee of a call; anywhere else — an operand, an
argument, a method receiver, the base of a dotted path — it is a config key, however it is
spelled. `_expressions._function_name` is the one place that tells them apart, and validation,
evaluation, reference collection and the mount-time `_Prefixer` all ask it:

| Expression, with `max: 3` | Value |
|---|---|
| `${max}`, `${max + 1}` | `3`, `4` |
| `${max(max, 5)}` | `5`, the builtin called on the key |
| `${max}` with no `max` key | `MissingReferenceError`, hinting that `max` is called as `max(...)` |
| `${len.a}` | the key `len.a`, and a dependency like any other |
| `${str.upper()}` | the method called on the key `str` |

Before BUG-120 a function name was exempted wherever it appeared, so `${max}` yielded the
builtin and an interpolation printed `<built-in function max>`, a path rooted at one was no
dependency (an unresolved `${...}` could leak out of it) and a mounted fragment's `${max}` was
never prefixed. A bare function value has no use here — nothing in the whitelist takes a
function — so reading it as a key loses nothing. The one spelling it breaks is a function as
a method receiver, `${str.join(',', xs)}`, which `${','.join(xs)}` replaces.

The rule is syntactic, which is what lets `_Prefixer` apply it at mount time, inside `merge()`,
without seeing the data. Precedents for keeping functions and keys apart by call position:
JMESPath, CEL and HCL (Terraform) — a bare identifier is always a field or variable there.

Rejected:

- **Refusing a function name anywhere but as a callee.** A root key named `min`, `max` or `len`
  is common (`limits: {min: 0, max: 10}`) and could then never be referenced bare, including
  from inside a mounted fragment, where every reference is bare.
- **Real key wins, at evaluation** (simpleeval, Python's own scoping). Which one a name means
  then depends on the data, which `_Prefixer` and `_collect_names` cannot see, and `${max}`
  with no key would still yield the builtin.
