# A call replaces what lies below

A dict holding the `call` key, where the type reads it as a call, discards what a lower layer set at its node during the merge, as a union tag does ([a class tag replaces](class-tag-replaces.md)): `p: {a: 5}` in one file and `p: {call: pkg.square}` in a later one merge to `{call: pkg.square}`, and a lower list does not become the call's `__base__`.
The rule holds at every depth, the root included; whether the key is a call there is the type's to say ([the type decides](the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines)).
A layer holding only `args` still refines the call below it, and so does one whose `call` holds a dict with no opener, which refines the nested target.
Plain data written over a call stays the error it is: `{call: square, a: 3}` holds a key no call takes, and `build()` refuses it.

Why: a call is a finished value.
Its spec is the opener and the mapping under `args` ([a computation's arguments nest under args](a-computations-arguments-nest-under-args.md#a-computations-arguments-nest-under-args)), so no key a lower layer left beside it can belong to it: kept, it is either refused by the call or, before `args`, silently taken as an argument (BUG-190).
FEAT-28 made `call:` a spec on every typed field and left the merge reading the key as data.

BUG-190's fix told the call by key alone (`_merge._is_call_dict`), so a higher layer writing `call` where the type holds it as data, a `dict` field or a struct with a member named `call`, dropped what the lower layers gave the node.
BUG-232 moved the decision to the type, which removed that cost; the alternatives weighed then are in [the type decides](the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines).

Rejected:

- **Defer to `build()`**, the merge carrying the lower value under a marker for the type-aware default layer to drop under a typed call and merge back otherwise.
  It loses no data where the type holds `call` as data, but it needs a new marker in what `merge()` returns, a reserved file key so `dump_file(merge())` reads back, and every `${...}` that reads a key under the marker would have to see through it, the cost deferred list patches had until BUG-220, where `build()` now applies them before resolution ([a pending list op is applied before resolution](a-pending-list-op-is-applied-before-resolution.md#a-pending-list-op-is-applied-before-resolution)).
- **Replace on nested nodes only**, leaving the root to merge.
  It would break the rule the union tag already follows at the root.
- **Let plain data over a call replace it.**
  A patch has nothing to apply to while the value is unknown, but `{a: 3}` is exactly what someone used to the flat grammar writes to refine an argument, so replacing would hide that mistake; the loud refusal stays.

Precedents: confarg's own union tag and cast pin, which also replace what lies below.
Kubernetes' strategic merge patch spells a replacement by a key in the patch itself (`$patch: replace`).
OmegaConf, under Hydra, merges a node holding `_target_` key by key, so switching the target in a later config keeps the old target's arguments, which then fail as unexpected keywords: the pitfall this rule removes.
