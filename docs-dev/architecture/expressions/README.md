# Expressions and variable interpolation

`${...}` in the string values of a plain nested dict, resolved after every source has merged.
Implementation: `dictexpr/**`, which imports only the standard library and
`confarg.exceptions`.

| Note | What it holds |
|---|---|
| [resolution.md](resolution.md) | why the engine knows nothing about channels, the five steps `resolve_expressions` runs, which expressions a reference waits for, and how a runtime failure or a refusal names its expression |
| [values-and-references.md](values-and-references.md) | when an expression keeps its Python type, where it ends, how a path is spelled, why a position is a sequence of segments, and what referencing a whole subtree substitutes |
| [safety-model.md](safety-model.md) | the whitelisted AST: which nodes and which calls, what the whitelist therefore excludes, why a function is named only by a call, a method runs only on a string and a dot reads a key, never an attribute |
| [deferral-rule.md](deferral-rule.md) | every value gate before `build()` must let an expression through, and must ask one predicate |
| [reference-anchoring.md](reference-anchoring.md) | the three anchors, which of them is a rewrite and which is resolved late, and the constraints that keeps |
