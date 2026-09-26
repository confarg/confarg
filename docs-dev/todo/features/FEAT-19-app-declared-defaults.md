# FEAT-19 — App-declared defaults, mounted at the type that declares them

**Where:** `src/confarg/_pipeline.py`, `src/confarg/_api.py`, `src/confarg/cli/_spec.py`, plus a new
core marker module · **Filed:** 2026-09-21 · *(inferred — design settled with the maintainer, no
code written)*
**Effort:** L · **Risk:** medium · **Impact:** behavior

An application that composes stand-alone configurations knows things about the composition that
none of the composed types know. A pipeline whose `prepare` and `eval` nodes are both configured by
a reusable type carrying `project_id` knows the two are one knob; a training run whose `data` and
`model` both carry `batch_size` knows the same. confarg has no way for the app to say so.

The only factorization on offer is `locals:` ([08-locals.md](../../architecture/08-locals.md)), and
declaring a local is deliberately a config-file privilege — it is the tool for a link the app does
*not* know about, introduced by whoever writes the file. Using it here inverts the ownership: the
app has to ask its users to write the app's own invariant, in their file, and a user who omits it
silently gets two independent knobs with no error. Nothing in the type says the two are related.

## The shape

A declared default is **not a new kind of value**. It is a configuration fragment shipped by the
app, mounted at the node that declares it, merged below every source — same fragments, same
anchoring, same deep merge, same expression engine. The only new thing is a *source* of fragments:
the target type itself.

```python
@dataclass
class Config:
    __confarg_wiring__ = (          # class-level form: same markers, the class as mount point
        Default({"prepare.project.project_id": "${project_id}"}),
    )
    project_id: int
    prepare: Annotated[Prepare, Default({"project.project_id": "${project_id}"})]
    eval:    Annotated[Eval,    Default({"project.project_id": "${project_id}"})]
```

| Aspect | Rule |
|---|---|
| Marker value | a scalar on a leaf field, a fragment on a struct field |
| Path spelling | nested dicts **and** dotted keys, resolved by walking the target with the *real field wins* rule the CLI already uses ([03](../../architecture/03-cli-parsing.md#real-field-wins)); nesting is the escape for a literal dotted key |
| Mount point | the node that declares it — the marked field, or the class |
| Anchoring | bare references resolve **in the class that wrote them**, one level above a field marker's mount, applied with `dictexpr.prefix_references` |
| Priority | below every source, below `files=`: any file, env or CLI value wins |
| Values | any value, not only expressions |
| Absent nodes | fill holes, never materialize (below) |
| Layering | composer wins: a class's own wiring is the base, each composing class overrides its children's |
| Several markers | `Annotated` is variadic and a field may carry more than one; `cli/_spec.py`'s `_get_field_meta` returns the *first* match today and has to become a collector |
| Required-ness | a field with a declared default is no longer required |

The anchoring rule is the whole design in one line: it is
[07-expressions.md#reference-anchoring](../../architecture/07-expressions.md#reference-anchoring)'s
"a bare reference means what it means in the file that wrote it", transposed from files to classes.
Ownership is transitive, so `Config` may wire anything in its subtree at any depth — and a reused
`Project` still cannot reach the root, because it does not know where it is mounted. **You can only
wire what you own**, and the anchor enforces that rather than documenting it.

`Default` is also the only way to make a value *referenceable*: a Python default never enters the
merged dict (`construct` applies it last), so `${data.batch_size}` over a Python-defaulted field
raises `MissingReferenceError`. A Python default is how a class defaults its own field; a declared
default is how a composer defaults its children's, and it is visible to expressions. The split is
ownership, not value kind.

## Fill holes, never materialize

> Descend into a node if it is present in the merged data, **or** if construction would have to
> build it anyway (a required field with no default). Stop where absence is a legal outcome: an
> optional field, or any Python default.

With `prepare: Annotated[Prepare | None, Default({"project.project_id": "${project_id}"})] = None`:

| Input | `prepare` |
|---|---|
| nothing | `None` — nothing wrote under `prepare`, and absence is legal |
| `--prepare.model_path m.pt` | filled: `prepare.project` is absent but required, so it is built anyway and its hole takes the root knob |
| the same, plus `--prepare.project.project_id 9` | `9` — an explicit value outranks the layer |
| `--prepare '{}'` | `MissingFieldError` on `model_path`: the node was turned on explicitly and is incomplete |

Both halves are needed. The first keeps an optional subtree from switching itself on; the second is
what makes a deep default apply at all once its owner is present. The side effect is that
`prepare: {}` becomes the explicit "enable this node with everything the app can derive" gesture, in
every channel, with no new syntax.

## What decides the implementation

- **`resolve()` is type-blind** — it takes a dict and no target — so an app-supplied `${...}` has to
  be in the dict before it runs, i.e. injected by `merge()`. Injecting in `build()` alone breaks the
  three-step seam `merge → resolve → from_dict`
  ([01](../../architecture/01-pipeline-and-contracts.md#public-api-seams)). `build()` applies the
  same pass for a hand-assembled dict; over `merge()`'s output it is idempotent.
- The pass belongs beside `_apply_locals_layer` in `_pipeline._merge_sources`, which is the
  precedent for a target-guided walk over the three source dicts and the one place all five
  front-ends delegate to — so cross-channel parity is free
  ([09](../../architecture/09-invariants.md#cross-channel-parity)).
- It has to be *computed* after the sources are merged, so a union's variant is known, and *merged*
  underneath them.
- `Annotated` is the sanctioned channel for per-field extras
  ([10](../../architecture/10-design-decisions.md#no-custom-types-required)), which is what keeps
  this out of the "no custom types" budget; the ticket is an instance of the umbrella
  [FEAT-6](FEAT-6-annotated-field-metadata.md). The class-level form is an unannotated class
  attribute, so it is not a dataclass field and needs no import at the declaration site — and it is
  the only form available to the root class, which has no field to hang an `Annotated` on.

## What acceptance costs

`merge()` would no longer return the input "exactly as written": it also carries the app's declared
defaults, and its docstring and
[01-pipeline-and-contracts.md](../../architecture/01-pipeline-and-contracts.md) say otherwise today.
The trade is deliberate — it is what lets `dump_file(merge(...))` capture the *effective*
configuration with `${...}` intact, as a fragment that can be mounted elsewhere — but it is a
documented contract, and changing it is part of accepting this.

Two boundaries to state rather than solve: a fragment cannot address list elements (`list[Prepare]`
has no stable address for one, and broadcasting to every element is a second addressing rule); and a
composer that names a component's internals is coupled to them, so renaming `Prepare.project` makes
the fragment stop matching, surfacing as an unknown field at `build()` rather than at import.

## Rejected on the way here

- **Interpolation as a plain dataclass default**, OmegaConf's `II("project_id")`. Defaults never
  reach the merged dict, so it cannot resolve; and a reusable sub-config cannot anchor a reference
  outside itself.
- **A parent anchor** (`${^.x}`) so a component could reach its parent, *as a way of reaching
  outside itself*. It would make a reusable type's meaning depend on how deep it is mounted.
  Note that `${..x}` since shipped ([07](../../architecture/07-expressions.md#reference-anchoring))
  — it is clamped at the file that wrote it, so it cannot reach outside a component, and this
  rejection stands for the injection this ticket describes.
- **Call-site links with a compute function**, jsonargparse's `link_arguments`. The compute function
  is a second wiring mechanism competing with the expression engine
  ([09](../../architecture/09-invariants.md#delegate-to-the-canonical-function)); without it, it is
  this injection with the keys reversed and no anchoring.
- **Broadcast from the knob** (`Annotated[int, Broadcast("prepare.project_id", …)]`, the shape of
  Kustomize's `replacements`). Sugar over the same injection, but as a push it has to restate the
  merge precedence it is not allowed to violate.
- **`__post_init__` fan-out in the app.** Forces the reused types to make the shared field optional,
  destroying the contract the reuse was for.

Precedents: Hydra's defaults list composes fragments and lets the composing config override what it
pulls in, which is where *composer wins* comes from; OmegaConf offers the consumer-side half with
`II`/`SI`; Terraform and Bicep wire every module parameter at the composition point and never
inherit. Nothing found declares the wiring in the type with the anchor following the declaration.

Nothing blocks an application today: the same fragment can be shipped as a packaged file and passed
first in `files=`. What this adds is the invariant living in the type instead of in packaged data,
visible in `--help`, with no file to find at runtime.
