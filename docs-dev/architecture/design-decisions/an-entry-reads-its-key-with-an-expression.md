# An entry reads its key with an expression

An entry of a `dict[str, Foo]` whose `Foo` carries a `name` is named after the key it is filed under by writing `name: ${key(.)}` in it.
`key` is a path function: it reads the position its argument spells, never the value there ([expressions](../expressions/safety-model.md#a-path-function-reads-a-position-not-a-value)).
The link lives in the configuration, so it travels with a dumped fragment, any channel can write it (`--foo.api.name '${key(.)}'`), and an entry that writes its own name simply holds no expression.

What it costs: each entry writes the expression.
A class default cannot carry it, since a default string is text ([a field default is the base layer](a-field-default-is-the-base-layer.md#a-default-string-stays-text)), and nothing yet reaches every entry of a dict ([limitations](../limitations.md#expressions)).

Precedents: XPath's `name(.)` and `name(..)` name the context node and its parent, and jq's `path(f)` reads its argument as a path rather than a value.
Terraform's `each.key` and CUE's `[Name=string]: {name: Name}` exist for the same "name an entry after its key" case.
OmegaConf has nothing built in; users register a resolver reading `_parent_._key()`.

Rejected:

- **A type-level marker**, `foo: Annotated[dict[str, Foo], KeyInto("name")]` on the dict field, or `name: Annotated[str, FromKey()]` on the entry's own field.
  Every entry would be named without writing anything, but the link would live in the type rather than in the configuration, where the maintainer wanted it.
  The field-side variant also makes `Foo` mean something different in a dict, in a list and at the root.
- **The spelling `name(.)`**, after XPath.
  The field it fills is very often `name` itself, and `name: ${name(.)}` reads as a self-reference.
- **A marker of its own** (`${.^}`).
  It needs a new token in `_anchor_markers` and reads as nothing a Python reader knows, where a call already parses.
- **Reading `${.}` and taking its key.**
  A reference is a path to a value, and `.` from `name` is the node that holds the expression: the cycle any reference to an ancestor is ([resolution](../expressions/resolution.md#a-reference-reads-everything-its-path-reaches)).
