# Safety model

Expressions come from config files, env and argv, so they are evaluated by a small
interpreter over a whitelisted AST, never `eval`:

- allowed nodes: constants, names, attributes, subscripts, arithmetic, comparisons,
  boolean ops, conditional expressions, calls (`_ALLOWED_NODES`);
- calls only to whitelisted free functions (`abs min max round ceil floor str int float bool
  len`) and string methods (`upper lower strip split replace startswith endswith join`) called
  on a string; no indirect calls;
- no attribute starting with `__`;
- consequently no literals for lists/dicts/sets, no slices, no comprehensions, no lambdas, no
  f-strings. A `}` inside a string literal is fine: delimiting is lexical, not a regex
  ([values and references](values-and-references.md#delimiting-an-expression)).

`a.b` and `a['b']` are first tried as a config path; only if that fails are they a real
subscript (an index into a string), and a miss is reported as a missing field rather than a
`KeyError` ([values and references](values-and-references.md#spelling-a-path)). Neither
reaches `getattr` ([below](#a-dot-reads-a-key-never-an-attribute)), so `['__class__']` is a key
like any other.

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

## A method is a string method

A call `<receiver>.<name>(...)` is a method call, `_expressions._method_name` is the one place
that says so, and validation, evaluation and reference collection all ask it. Each half of the
whitelist is checked where it can be known:

- **the name, at validation**: it must be one of `_SAFE_METHODS`. A free function's name is no
  method, so `${d.max(5)}` is refused as `Method 'max' is not allowed`;
- **the receiver, at evaluation**: it must be a `str` (a CLI or env token is one). The type is
  only known once the receiver is evaluated, so `${when.replace(2000)}` on a YAML date,
  `${blob.upper()}` on bytes or `${d.max(5)}`'s `Decimal` are refused there, as
  `UnsafeExpressionError`, not as a runtime failure.

The callee is never a config path: the receiver is evaluated and the method looked up on it, so
`${x.upper()}` with `x: {upper: ...}` is refused rather than calling whatever the key holds, and
the call depends on `x`, not on `x.upper`.

Before BUG-122 the name could also be one of `_SAFE_FUNCTIONS`, any receiver was accepted, and
the callee was read as a path first. That reached `Decimal.max`, `date.replace` and — on a
`pathlib.Path` value — `Path.replace`, which renames a file; and a whitelisted name could call
any callable a dict held under it. No string has a method named like a whitelisted function,
and a non-`str` receiver has no use the whitelist was written for, so the narrower rule loses
nothing the safety model promised.

Precedents check the receiver too: CEL resolves a member function per receiver type and fails
with *no such overload* on any other; Jinja2's sandbox decides attribute safety per object at
runtime (`is_safe_attribute(obj, attr, value)`), not per name. simpleeval, which filters
attributes by name alone, is the counter-example, and has needed name-blocklist fixes for
escapes through `str.format` and `format_map`, which it now blocks by name.

Rejected: **refusing a non-`str` receiver at validation.** Validation sees syntax, not data; the
receiver may be a path, a subscript or a call whose type no rule could predict.

## A dot reads a key, never an attribute

`.x` is the constant subscript `['x']`, on a path and off one: when no config path answers
`a.b`, evaluation indexes the evaluated `a` by the key `"b"`, exactly as it would for `a['b']`.
`_expressions._eval_path_or` is the one evaluator of both nodes, so a dot and a subscript cannot
disagree on what they reach:

| Expression | Value |
|---|---|
| `${svc[k].host}`, `${(a if c else b).host}` | the key `host` of the dict the base evaluates to |
| `${n.upper}` | `MissingReferenceError`, hinting that `upper` is called as `n.upper(...)` |
| `${p.unlink}` on a `pathlib.Path`, `${d.year}` on a date | `MissingReferenceError`: a value's attributes are no keys |

Before BUG-125 the fallback was `getattr`, with only dunders refused. On a string that only ever
yielded a bound method, which an interpolation printed as `<built-in method upper of str object
at 0x…>` — the leak BUG-120 closed for a bare function name. On any other value it reached every
public attribute by name, whatever the type, and a bound method such as `Path.unlink` could reach
a `Callable` field. The same fallback also made `.x` and `['x']` disagree off a path:
`${svc[k].host}` failed with `'dict' object has no attribute 'host'` while `${svc[k]['host']}`
read the key. A method may only be called, and only on a string
([above](#a-method-is-a-string-method)); a data attribute such as a date's `year` had no test,
no documented use and no whitelist entry, so the narrower rule loses nothing the safety model
promised.

Precedents expose the data's fields only, never host-language attributes: JMESPath and CEL
select fields of the document, OmegaConf's `${a.b}` is a node path, and JavaScript, jq and Jinja2
read `a.b` as `a['b']` (Jinja2 falls back on `getattr` only because its data are Python objects,
and its sandbox then has to vet each attribute).

Rejected:

- **Refusing a callable result only** (Jinja2's sandbox, `is_safe_attribute`). It keeps a date's
  `year`, but leaves every public data attribute of every type reachable — a surface decided per
  type, which the whitelist never audited — and keeps `.x` and `['x']` apart off a path.
- **No fallback for a dot at all.** An attribute no path answers would always be a missing
  field, so `${svc[k].host}` would stay unreadable while `${svc[k]['host']}` reads it.
