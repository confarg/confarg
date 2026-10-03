# Stages and intermediate representations

## The pipeline

```
argv  ──▶ _parse_cli ─┐                        build()
env   ──▶ _parse_env ─┼─▶ _merge_sources ─▶ resolve_expressions ─▶ strip locals ─▶ construct ─▶ T
files ──▶ _files ─────┘   (_pipeline.py)      (dictexpr)                           (typedload)
                          config < env < CLI
```

`load()` = `merge()` + `build()`. `build()` = `resolve_expressions` + `_strip_locals` +
`typedload.construct` (with `__root__` unwrapping for non-struct targets).

## Plain dicts as the intermediate representation

Every stage before construction produces and consumes plain nested `dict`s. There are two
intermediate representations, both plain dicts:

1. the **merged dict** — the union of all sources, `${...}` still literal (`merge()`);
2. the **resolved dict** — same shape, expressions evaluated (`resolve()`).

Why: it makes the API decomposable (stop, inspect, persist or hand-assemble at any seam),
keeps the engines independent of where data came from, makes round-tripping trivial, and
lets the contract tests assert byte-equality across front-ends.

Cost: the dict is untyped and stringly keyed, so structural mistakes surface late (in
`build()`), and sentinel keys (`__root__`, `__cast__`, `+`, `-`, `*`, `~`, …) live in the same
key space as user data. See [FEAT-3](../../todo/features/FEAT-3-reserved-sentinel-key-registry.md).
