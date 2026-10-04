# Expressions and variable interpolation

`${...}` in the string values of a plain nested dict, resolved after every source has merged.
Implementation: `dictexpr/**`, which imports only the standard library and
`confarg.exceptions`.

| Note | What it holds |
|---|---|
| [resolution.md](resolution.md) | why the engine knows nothing about channels, the five steps `resolve_expressions` runs, and which expressions a reference waits for |
| [values-and-references.md](values-and-references.md) | when an expression keeps its Python type, where it ends, how a path is spelled, and what referencing a whole subtree substitutes |
| [safety-model.md](safety-model.md) | the whitelisted AST: which nodes and which calls, what the whitelist therefore excludes, why a function is named only by a call and a method runs only on a string |
| [deferral-rule.md](deferral-rule.md) | every value gate before `build()` must let an expression through, and must ask one predicate |
| [reference-anchoring.md](reference-anchoring.md) | the three anchors, which of them is a rewrite and which is resolved late, and the constraints that keeps |
