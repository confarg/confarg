# Stages and intermediate representations

## The pipeline

```text
argv  ──▶ _parse_cli ─┐                        build()
env   ──▶ _parse_env ─┼─▶ _merge_sources ─▶ lay defaults ─▶ resolve_expressions ─▶ drop untouched ─▶ strip locals ─▶ construct ─▶ T
files ──▶ _files ─────┘   (_pipeline.py)    (_default_layer)  (dictexpr)                                              (typedload)
                          config < env < CLI
```

`load()` = `merge()` + `build()`.
`build()` = `_default_layer.lay_defaults` + `resolve_expressions`

+ `drop_untouched` + `_strip_locals` + `typedload.construct` (with `__root__` unwrapping for non-struct targets).
  The target's field defaults are the layer below every source, laid in `build()` rather than in `merge()` ([design decisions](../design-decisions/a-field-default-is-the-base-layer.md#a-field-default-is-the-base-layer)).

## Plain dicts as the intermediate representation

Every stage before construction produces and consumes plain nested `dict`s.
There are two intermediate representations, both plain dicts:

1. the **merged dict** — the union of all sources, `${...}` still literal (`merge()`);
2. the **resolved dict** — same shape, expressions evaluated over the target's field defaults, the patches pending over a default applied (`resolve(target, data)`).

Why: it makes the API decomposable (stop, inspect, persist or hand-assemble at any seam), keeps the engines independent of where data came from, makes round-tripping trivial, and lets the contract tests assert byte-equality across front-ends.

Cost: the dict is untyped and stringly keyed, so structural mistakes surface late (in `build()`), and reserved keys (`__root__`, `__cast__`, `__include__`, …) live in the same key space as user data: a file reads them as its own and the other channels may not write them ([config files](../config-files/reserved-keys.md#reserved-file-only-keys)).
The list ops alone are kept out of it, as markers no channel types ([deep merge](deep-merge.md#no-channel-types-an-op)).
