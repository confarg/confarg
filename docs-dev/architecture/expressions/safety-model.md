# Safety model

Expressions come from config files, env and argv, so they are evaluated by a small
interpreter over a whitelisted AST, never `eval`:

- allowed nodes: constants, names, attributes, subscripts, arithmetic, comparisons,
  boolean ops, conditional expressions, calls (`_ALLOWED_NODES`);
- calls only to whitelisted free functions (`abs min max round ceil floor str int float bool
  len`), the path function `key` ([below](#a-path-function-reads-a-position-not-a-value)) and
  string methods (`upper lower strip split replace startswith endswith join`) called on a
  string; no indirect calls;
- no attribute starting with `__`;
- consequently no literals for lists/dicts/sets, no slices, no comprehensions, no lambdas, no
  f-strings. A `}` inside a string literal is fine: delimiting is lexical, not a regex
  ([values and references](values-and-references.md#delimiting-an-expression)).

`a.b` and `a['b']` are first tried as a config path; only if that fails are they a real
subscript (an index into a string), and a miss is reported as a missing field rather than a
`KeyError` ([values and references](values-and-references.md#spelling-a-path)). Neither
reaches `getattr` ([below](#a-dot-reads-a-key-never-an-attribute)), so `['__class__']` is a key
like any other.

## A computed value is bounded

Expressions come from argv and the environment as well as files, so a value a few characters long must not stall the host. Before BUG-146 nothing bounded what an expression computed: `${10 ** 10 ** 7}` took 17 s and `${9 ** 9 ** 9}` never finished, `${'ab' * 10 ** 8}` allocated 200 MB, and so did `%` formatting (`'%0100000000d' % 1`), `replace` (`s.replace('', s)`), `join`, a list repeated, and chains across keys, each doubling or squaring the one before. Every value an expression **computes** is now bounded, and so is their total:

| Bound | Limit | Measured as |
|---|---|---|
| a computed `int` (a `bool` included) | `sys.get_int_max_str_digits()` digits, read when the expression runs (4 300 by default); the length cap when that limit is off (0) | its decimal digits |
| a computed `str`, `bytes`, list, tuple, dict or set | 1 000 000 | its characters, bytes or items |
| a computed `Path` | 1 000 000 | the characters of its text |
| everything one resolution computes | 10 000 000 | each computed value's size, summed |

- **What counts** is a result an operator, a function or method call, or an interpolation produces (`_charged`, the one place a value is measured, against its cap and the budget). A read (`${a.b}`, `${s[0]}`) and a selection (`${a if c else b}`, `${a or b}`) hand back a value that already exists, and count nothing: a hundred `${big}` cost no more than one. A comparison yields a `bool`, which is not counted either. Every result counts whatever object Python returns, so `${big + ''}` costs `len(big)` though CPython hands `big` back: the rule reads the syntax, not the allocator.
- **Estimated before computing, where computing is the cost** (`_check_binop`, `_check_method`): a power of two ints, by `exponent × log10|base|` digits, computed and measured exactly within a digit of the cap; a repetition, by `len × times`; `%` on a `str` or `bytes`, by the template's length plus every width and precision it writes or takes for a `*`, the arguments' own text being bounded by their caps; `replace`, by the occurrences found times the growth; `join`, by the items' lengths and the separator's. Everything else costs no more than its operands, and is measured once computed.
- **A type no source can produce is trusted.** A file, a variable and a flag produce `str`, `bytes`, numbers, `bool`, `None`, dates, lists and dicts, and an `Enum` or registered leaf only as the object an expression reads it as ([values and references](values-and-references.md#a-typed-leaf-reads-as-its-object)). Any other object — a `Fraction` in a caller's data, a registered type's instance — came from the application: its operators run, and it measures 1 ([limitations](../limitations.md#expressions)).
- **A refusal is an `UnsafeExpressionError`**, quoting the expression and naming the size and the limit (`Result would hold 20000000 characters, over the limit of 1000000 characters`); the budget's names the expression that crossed it.
- **The limits are fixed.** No channel may raise one, since every channel can carry the value they protect against; the `int` limit moves with the interpreter's own, which the application sets.

Precedents: simpleeval caps an exponent at `MAX_POWER` (4 000 000, timed: `9**9**6` took over 30 s) and a string produced by `+` or `*` at `MAX_STRING_LENGTH` (100 000, a round default with no recorded rationale, meant to be overridden); CPython limits int↔str conversion to 4 300 digits (CVE-2020-10735); Kubernetes CEL bounds one expression's cost (`PerCallLimit`, 1 000 000) and an object's total (`RuntimeCELCostBudget`, 10 000 000).

Rejected:

- **Capping the operands of `**` and `*` alone** (simpleeval). `%`, `replace`, `join`, a repeated list and every chain across keys stay unbounded, and the operand cap refuses cheap powers (`2 ** 5_000_000`) while it lets an expensive one through (`999999 ** 3_999_999`).
- **A cap per value without a total.** Each key interpolating a value just under the cap (`k: ${big}x`) uses another megabyte: a 1 MB file of such lines asks for 100 GB.
- **Refusing operators on every type confarg does not measure.** No source can produce one, so the refusal guards against nothing a configuration can write, and it refuses the application's own `Decimal` arithmetic.
- **Refusing `%` on strings.** It is the one way to zero-pad (`'%04d' % i`); bounding its widths is a short parser.
- **Configurable limits.** A knob is an API surface with five front-ends to reach, and none was asked for; the `int` limit already follows the interpreter.

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

## A path function reads a position, not a value

`${key(p)}` is the key the path `p` is filed under: `${key(.)}` at `foo.web.name` is `"web"`, `${key(..)}` is `"foo"`, and a list element's key is its position, an `int` (`${key(xs[-1])}` is the last index, as `_step` names it). It is what lets an entry be named after the key it sits under without writing that key twice:

```yaml
foo:
  web:
    name: ${key(.)}   # "web"
```

The argument is a path, never a value. Reading `.` from `name` would read the `foo.web` node that holds the expression, the cycle any reference to an ancestor is ([resolution](resolution.md#a-reference-reads-everything-its-path-reaches)); `key` reads where the node is, not what it holds. So `_PATH_FUNCTIONS` is a table of its own beside `_SAFE_FUNCTIONS`, and each step treats its argument as syntax:

- **validation** (`_validate_path_call`) takes exactly one positional argument that spells a path: a name, a dot run, a root marker, or a chain of dots and constant subscripts. A computed subscript (`key(svc[k])`), an operand or a constant spells none and is refused;
- **reference collection** (`_collect_names_from_call`) collects nothing from it, so it is no dependency and resolves in the first batch;
- **evaluation** (`_expressions._eval_key`, the one answer to "what key is this position filed under?") walks to the container with `_step`, the walk a read takes, so a miss reads `Field 'foo.nope' not found` as a read of it would.

Nothing else learns of it. A dot run is resolved by `_AnchorResolver` before evaluation, as for any reference; `_Prefixer` prefixes a bare path's base, which keeps the last segment (`key(foo)` in a fragment mounted at `sub` is `key(sub.foo)`, still `"foo"`); `check_anchor_depth` clamps `key(..)` as it clamps `${..x}`; and `merge()` keeps the text as written ([reference anchoring](reference-anchoring.md#a-relative-reference-is-never-serialized-as-an-absolute-path)). At a file's top level, `key(.)` names the key the file is mounted under: that is the name of the mount point, not a value outside the file.

Two positions have no key, and are refused at evaluation with an `ExpressionEvalError`: the configuration root (`${key(::)}`, or a dot run that climbs to it), and an item a pending list op holds (`xs.__append__.0`), whose index is only known once construction applies the op. A YAML integer key answers to the integer subscript, as a read falls back on it ([values and references](values-and-references.md#spelling-a-path)).

`key` is a function only as a callee ([above](#a-function-is-named-only-by-a-call)): `${key}` reads a key named `key`.

Why an expression rather than a marker on the type, and the spellings rejected for it: [design decisions](../design-decisions/an-entry-reads-its-key-with-an-expression.md#an-entry-reads-its-key-with-an-expression).
