# FEAT-20 — Derived values that cannot be made inconsistent

**Where:** `src/confarg/_api.py` (a post-resolution pass), plus the marker module of
[FEAT-19](FEAT-19-app-declared-defaults.md) · **Filed:** 2026-09-21 · *(inferred — design settled
with the maintainer, no code written)*
**Effort:** M · **Risk:** medium · **Impact:** behavior

[FEAT-19](FEAT-19-app-declared-defaults.md) gives an application a way to *default* one node's field
from another's. Sometimes the equality is not a convenience but an invariant: a training run whose
`data.batch_size` and `model.batch_size` disagree is not a configuration with an unusual value in
it, it is a configuration that cannot run. A default cannot say that — it is overridable by
construction, and overriding exactly one of the two is what breaks the invariant.

`Derived` is `Default` plus one assertion:

```python
@dataclass
class Config:
    batch_size: int
    data:  Annotated[Data,  Derived({"batch_size": "${batch_size}"})]
    model: Annotated[Model, Derived({"batch_size": "${batch_size}"}), Default({"seed": 0})]
```

It is injected identically — same fragment, same mount, same anchoring, same lowest priority — and
then, after `resolve_expressions`, each declared expression is re-evaluated against the resolved
dict and compared with the value sitting at its path. A mismatch raises. So `--batch_size 64` sets
both; `--model.batch_size 64` alone is an error naming the source; and writing both to the same
value is accepted, because the invariant holds. Nothing is silently discarded, which is the failure
mode an "override wins" or "derived wins" rule would have.

## Why an assertion rather than a read-only field

jsonargparse's `link_arguments` removes the target argument from the parser, so it cannot be set at
all. That is the stronger guarantee and it fails earlier, at parse time, but it costs more than it
looks:

| | Read-only | Default + assertion |
|---|---|---|
| Where it can be enforced | `merge()` only — refusing a write means knowing a source wrote it, and only `_merge_sources` holds the three source dicts apart | `build()` **and** `from_dict()`: comparing two resolved values needs no provenance |
| A hand-assembled dict | unprotected | protected |
| `dump()` → `load()` | breaks — the dump writes the derived path, which the reload then refuses, so `dump()` would have to learn to omit derived fields ([01](../../architecture/01-pipeline-and-contracts.md#public-api-seams)) | unchanged: the dumped values agree, so the assertion passes |
| A correct but redundant value in a file | refused | kept, which is often how a configuration is meant to read |

Provenance is the crux. confarg has none ([FEAT-8](FEAT-8-value-provenance.md)), so a refusal can
only live where the sources are still separate — one seam of three. An assertion compares values and
therefore holds everywhere a value is constructed. The read-only variant stays available later as a
stricter mode if the parse-time error turns out to be worth its cost; it is not the place to start.

## Notes for the implementation

- Depends on FEAT-19 and is worth nothing without it: the injection, the fragment shape, the dotted
  paths, the anchoring and the fill-holes rule are all inherited unchanged, and `Derived` differs in
  exactly one bit — whether the injected value is also asserted.
- The assertion runs after resolution and before construction in `build()`, and inside `from_dict()`
  for an already-resolved dict. It compares resolved values, so a whole-subtree link compares dicts.
- A cycle (`a` derived from `b`, `b` derived from `a`) is already a `CircularReferenceError` from the
  expression engine; nothing new is needed
  ([07](../../architecture/07-expressions.md#resolution-algorithm)).
- The error message has to name the source path, not just the mismatch: a user who typed
  `--model.batch_size 64` wants to be told to type `--batch_size 64`.
- `--help` should say a field is derived, and from what.

Precedents: jsonargparse's `link_arguments` (the read-only shape, used by LightningCLI for exactly
this `batch_size` case); CUE, where unification makes two constraints on one field an error unless
they agree, which is the assertion shape; pydantic reaches it with an after-validator, i.e. also by
comparing values after they are resolved rather than by forbidding the write.
