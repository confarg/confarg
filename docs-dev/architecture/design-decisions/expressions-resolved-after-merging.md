# Expressions resolved after merging, by a whitelisted interpreter

Late resolution lets any channel override an input of a file-defined formula
([expressions](../expressions/resolution.md#resolution-algorithm)). A small AST interpreter avoids `eval` on
untrusted configuration while covering arithmetic, conditionals and string methods. Precedents:
OmegaConf interpolation resolves lazily with registered resolvers; confarg instead offers a fixed
safe subset of Python syntax.
