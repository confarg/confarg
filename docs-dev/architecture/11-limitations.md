# Limitations

What confarg does **not** do, and why — the boundaries that follow from the design rather
than from work nobody has done yet. A user hitting one of these is not hitting a bug.

Anything open and actionable — defects, parity gaps, refactors, ideas, questions — belongs on
the boards in [`../todo/`](../todo/README.md), not here. When a ticket closes and the answer
turns out to be "we will not do that", the reason moves into
[10-design-decisions.md](10-design-decisions.md); when it changes what the library cannot do,
the boundary moves here.

## Expressions

- The grammar cannot express `}` inside an expression, collection literals, slices,
  comprehensions or lambdas. The whitelist is the safety model, not an unfinished parser
  ([07](07-expressions.md#safety-model)).
- A malformed expression contributes no dependency edges: it is not parseable, so nothing can
  be derived from it. The error surfaces at validation instead, with the expression text.
- `--config.<path>+` fragments keep their references anchored at the merged root, not at the
  mount point ([07](07-expressions.md#reference-anchoring)).
- A reference to a whole node substitutes that node's *value*, so each referencing site is
  constructed separately: two fields referring to one struct hold equal, non-identical
  objects. There is no way to share one instance
  ([07](07-expressions.md#referencing-a-whole-subtree)).
- In a `resolve()`d dict those paths do alias one sub-dict, so mutating it in place reaches
  every site that referenced it. Inspect and dump the resolved dict; do not edit it.

## Collections

- A whole value and a deeper key for the same field resolve last-write-wins, and the loser
  goes quietly. Only a `Callable` field's bare string survives the pair, being the shorthand
  for `{fn: …}`; at a union like `dict[str, str] | str`, where a scalar is legitimate but
  abbreviates nothing, `--d oops --d.c x` keeps only the subkey
  ([10](10-design-decisions.md#a-whole-value-followed-by-a-subkey-opens-rather-than-collides)).
- List deletion and negative indices need a base list to apply to: they are patches, and a
  patch has nothing to bite on in an empty document.
- Index-keyed lists must be gap-free, unless the element type is Optional — a gap would
  otherwise have to invent an element of an unknown type.

## CLI front-ends

- A multi-token flag is spelled per framework: space-separated for vanilla/argparse/cyclopts,
  repeated for click/cyclopts ([04](04-cli-adapters.md#list-syntax-divergence)).
- A fixed-arity flag (`tuple[X, Y]`, namedtuple) takes one whole-value token — `--pair
  '[13, 42]'`, `--pair '{"x": 13}'` — everywhere except click, whose options cannot vary their
  token count at parse time. click keeps `--pair 13 42`, which is the spelling a CLI user
  reaches for, and declines the JSON one
  ([04](04-cli-adapters.md#whole-value-flags)). Use a config file, an environment variable or
  the per-field flags (`--pair.x 13`) to set it whole under click.

## Subclasses

- `--help` lists a subclass's flags only once something has imported it: naming the class is
  what makes it visible, and nothing names it on a bare `--help`
  ([10](10-design-decisions.md#a-named-tag-is-imported-before-registration)). Import the
  plugin module, or name the class earlier on the same command line.

## Callables and serialization

- Owning-class detection for `fn: Class.method` fails for lambdas and for functions defined in
  nested scopes; a callable confarg did not build may not be serializable at all
  ([06](06-callables.md#round-trip)).
- Plain (non-dataclass) classes cannot be dumped by `dump()`. To serialize as fields, a class
  must store its `__init__` parameters as same-named attributes — confarg reads attributes, it
  does not replay constructor calls.
- Attribute docstrings used as `--help` text require the class source, which is unavailable for
  dynamically created classes ([04](04-cli-adapters.md#framework-neutral-flag-model)).
