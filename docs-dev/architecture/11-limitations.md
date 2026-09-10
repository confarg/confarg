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

## Collections

- List deletion and negative indices need a base list to apply to: they are patches, and a
  patch has nothing to bite on in an empty document.
- Index-keyed lists must be gap-free, unless the element type is Optional — a gap would
  otherwise have to invent an element of an unknown type.

## Callables and serialization

- Owning-class detection for `fn: Class.method` fails for lambdas and for functions defined in
  nested scopes; a callable confarg did not build may not be serializable at all
  ([06](06-callables.md#round-trip)).
- Plain (non-dataclass) classes cannot be dumped by `dump()`. To serialize as fields, a class
  must store its `__init__` parameters as same-named attributes — confarg reads attributes, it
  does not replay constructor calls.
- Attribute docstrings used as `--help` text require the class source, which is unavailable for
  dynamically created classes ([04](04-cli-adapters.md#framework-neutral-flag-model)).
