---
filed: 2026-10-06
where:
  - src/confarg/_callable.py
  - src/confarg/typedload/_construct.py
effort: XL
risk: high
impact: config
severity: major
---
# FEAT-27 — Replace the callable openers with `bind`, `call`, `class` and `classfn`

Umbrella for the redesign. The work is split into FEAT-28 to FEAT-34, chained by `blocked_by`.
This ticket records the design they implement; it is closed when the last of them is.

**Target grammar** (replaces `fn:`, `call:` as it is today, and the `bind:` kwargs dict):

| Form | Meaning |
|---|---|
| `x: pkg.T` | the target, with no arguments |
| `x: {class: pkg.T, <ctor kwargs>}` | an instance of `T`, checked to be a subclass of the field's annotation (or, under `Callable`, to be callable). Never stands in for `call:`. |
| `x: {call: T, <args>}` | `T(**args)`, or the function's return value. The result is checked against the annotation. Any field type. |
| `x: {bind: T, <args>}` | `functools.partial(T, **args)`. Partial only. |
| `x: {call: {classfn: C.m, <init>}, <args>}` | `C(**init).m(**args)` |
| `x: {bind: {classfn: C.m, <init>}, <args>}` | `partial(C(**init).m, **args)` |
| `x: {classfn: C.m, <init>}` | the bound method, as a callable |

Rules: a sibling of `call:` or `bind:` is an argument of the target. A sibling of `classfn:` is
an argument of the owner's constructor. `classmethod` and `staticmethod` paths need no owner, so
`classfn:` is for instance methods only. `class:` keeps its meaning of "the type I want" and is
restricted to compatible classes. `call:` is the general "run this and use its value" form.

**Decisions taken**

- `class:` stays as a keyword, because `foo: {call: mylib.Foo}` reads as a computation in the
  normal course of declaring parameters. `call:` may still build a class, but `class:` may not
  stand in for `call:`.
- Named targets only. `call:` does not evaluate expression strings. Evaluation order is decided in [resolution.md](../../architecture/expressions/resolution.md#calls-and-expressions-share-one-graph).
- `bind:` takes a target, never a kwargs dict. The old `bind:` kwargs form is removed, not kept
  alongside.
- Migration is a breaking config change (`impact: config`), so the old forms get a deprecation
  period, or a note in the changelog, before removal. FEAT-30 decides which.

**Not decided here**

- What a bare path to an instance method does: auto-instantiate with no arguments (today's
  rule), or raise. Today's rule is the default unless the maintainer says otherwise.

**Precedents**: Hydra `instantiate` (`_target_`, `_partial_`) for the call and partial split;
jsonargparse `class_path` for typed class targets (checked against the annotation). Neither has
a method form, which is why `classfn` is new.

See [callables.md](../../architecture/callables.md) for the current grammar, which is what the
work replaces.
