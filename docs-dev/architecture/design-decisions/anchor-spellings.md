# `::` spells the configuration root, a leading dot counts upwards

`${foo}` is anchored at the file, `${.foo}` at the value's own block (one level per dot) and
`${::foo}` at the configuration root ([expressions](../expressions/reference-anchoring.md#reference-anchoring)).

The dots follow OmegaConf, where `${.x}` is a sibling and `${..x}` a parent. An earlier design
had a single leading dot mean the *configuration* root, which inverted that convention and left
no spelling at all for a sibling — the one a list element needs, since it cannot know its index.

`::` was chosen for the root over `$.` (JSONPath, jq), `~` and a reserved `root.` namespace.
It means precisely "global scope" in C++, Ruby and Perl; being a different character from the
dot runs, absolute never reads as "a lot of relative"; and a reserved *name* would collide with
`root:`, a thoroughly plausible configuration key. Its one cost is that `::` is the spelling of
a slice step, settled by making it a marker only outside `[...]`.

Rejected: climbing more than one level *by a different mechanism* (`${^.x}`, a `super`). The dot
run already does it, and counting is the honest spelling of a thing that depends on depth.
