# Plan — A call's value is read by construction

**Drafted:** 2026-10-27 · **Status:** approved · **Tickets:** [BUG-297](../bugs/BUG-297-a-call-whose-value-is-the-same-call-or-holds-itself-recurses-raw.md), [FEAT-60](../features/FEAT-60-a-tuple-reads-where-a-list-reads.md), [BUG-293](../bugs/BUG-293-a-call-result-is-taken-unchecked-when-its-outer-class-matches.md), [FEAT-61](../features/FEAT-61-a-calls-value-is-configuration-on-an-any-and-a-callable-node.md)

A `call:` spec on a typed field takes its function's value "as it is" when `_callable._accepts` says the annotation already accepts it, and builds any other through construction ([call in a typed field](../../architecture/callables.md#call-in-a-typed-field)).
`_accepts` asks `isinstance` of the annotation's origin alone, so a value whose outer class matches is taken unchecked at every depth below it, and it disagrees with `_serialize._holds`, the dump's answer to the same question ([BUG-293](../bugs/BUG-293-a-call-result-is-taken-unchecked-when-its-outer-class-matches.md)).
Construction, the other half, refuses the one thing a function most often returns that no file can spell: an instance of the struct its node names, at any depth (`list[Model]` given `[Model(1)]`, run).

```text
t: tuple[int, int], call returns (1, 2, 3)          -> (1, 2, 3), unchecked
xs: list[int], call returns ['a', 'b']              -> ['a', 'b'], unchecked
ms: list[Model], call returns [Model(1), {'x': 2}]  -> [Model(1), {'x': 2}], a dict in a list of Model
box: Box[int], call returns Box('s')                -> Box('s'), unchecked
u: Model | int, call returns Model(7)               -> taken; but construction, asked, refuses it
build(D, {'a': Model(1)})                           -> TypeCoercionError: expected dict, got Model
n: int, call returns {'call': 'pkg.again'} (itself) -> RecursionError
```

The design was settled in one grilling session; each decision below names what it rejected and what the precedents do.
The examples use these classes:

```python
@dataclass
class Model:
    x: int = 0


@dataclass
class Sub(Model):
    y: int = 1


@dataclass
class Box[T]:
    item: T


@dataclass
class Other:  # unrelated to Model, same field names
    x: int = 0
```

## Decisions taken

### A call's value goes through construction, as `build()` data does

Every value a `call:` computes on a typed field is handed to construction, which reads it as it reads a dict a caller passes to `build()` or `from_dict()`: containers are rebuilt item by item, each item coerced or refused at its own path, a union ranked as any union is.
`_callable._accepts` is deleted; nothing takes a value "as it is" before construction has looked at it.

| a `call:` on | returns | today (run) | chosen (prototyped, run) |
|---|---|---|---|
| `ms: list[Model]` | `[Model(1), {'x': 2}]` | `[Model(1), {'x': 2}]`, silently | `[Model(1), Model(2)]` |
| `fs: list[float]` | `[1, 2]` | `[1, 2]` | `[1.0, 2.0]`, as [a float reads an int as its digits](../../architecture/design-decisions/a-float-reads-an-int-as-its-digits.md) reads a native int |
| `n: int` | `True` | `True` | refused, as `from_dict({"n": True})` is |
| `t: tuple[int, int]` | `(1, 2, 3)` | `(1, 2, 3)`, silently | refused: `expected 2 elements, got 3` |
| `xs: list[int]` | `['a', 'b']` | `['a', 'b']`, silently | refused at `xs[0]` |
| `ms: list[Model]` | the module-level list `SHARED` | `SHARED` itself | a new list holding the same `Model` objects |

The leaf changes follow rules already recorded for a Python value: a `datetime` under `date` is refused ([the date and time types](../../architecture/design-decisions/the-date-and-time-types-are-built-in-leaves.md) rejected the subclass rule), a `StrEnum` member under `str` reads as its text, a `Port(int)` stays a `Port`.

Rejected:

- **A deep hold, else construct**: take the value unchanged when it holds at every depth as a type checker reads it, otherwise construct all of it.
  A mixed `[Model(1), {'x': 2}]` is refused (`expected dict, got Model` at `ms[0]`), and the predicate cannot be `_holds`: `_holds(float, 1)` is `True`, so a top-level `1` under `float`, which construction turns into `1.0` today, would stay an int.
  It also walks the value twice, once to check and once to build.
- **The ticket's first direction**: take only a top-level instance of the struct the annotation names, construct every other value, with no instance taken below.
  `list[Model]` given `[Model(1)]`, the commonest shape of a factory's value, would start failing.

Precedent (run): pydantic, lax and strict, and msgspec's `convert` rebuild containers, take a model instance as it is (pydantic's `revalidate_instances='never'`, its default), turn `[1, 2]` under `list[float]` into `[1.0, 2.0]` and return a new list; msgspec and pydantic's strict mode refuse `True` as an `int`.
cattrs refuses the mixed list.

### Construction takes a built instance of what its node names

A node takes a value that is already what it names, as it is, through the reading its kind already has:

| node | takes as it is | by |
|---|---|---|
| a struct (`Model`, a plain class) | an instance of the class or of a subclass; for a generic struct, one whose members hold their bound types | `_holds`, the dump's predicate |
| a leaf with a coercion (built-in or registered) | what the coercion already takes as it is | the coercion, unchanged: `True` under `int` and a `datetime` under `date` stay refused |
| an unsupported leaf (`threading.Lock` on 3.13+, an unregistered `re.Pattern`) | an instance of the class | `isinstance`, the only reading the kind has |
| a namedtuple, a tuple, a set, a Callable, a `type[X]` | unchanged: each already reads a built value | — |

The rule is not gated: a struct instance in `build()` or `from_dict()` data is taken too, where it is refused today.
The merge never meets one, since a file, a variable and a flag cannot spell one, so only a caller's own data and a call's value carry one.

| `build(…)` | today (run) | chosen |
|---|---|---|
| `m: Model`, call returns `Sub(4)` | `Sub(4)` | `Sub(4)`: an instance needs no tag, its class is the tag's answer |
| `box: Box[int]`, call returns `Box('s')` | `Box('s')`, silently | refused, naming the member: `'s'` at `box.item` is no `int` |
| `m: Model`, call returns `Model(x='a')` | `Model(x='a')` | `Model(x='a')`: a non-generic class's constructor is its own contract |
| `build(D, {"a": Model(1)})` | `expected dict, got Model` | `D(a=Model(x=1))` |
| `build(D, {"a": Model(1), "n": "${a.x}"})` | `MissingReferenceError: … cannot traverse into Model` | the same refusal |
| `lock: threading.Lock`, `{call: threading.Lock}` | a fresh lock | a fresh lock |
| `m: Model`, call returns `Other(3)` | `expected dict, got Other Other(x=3)` | refused: `got an Other, which is no Model; a Model, or a dict of its fields, builds one` |

So `_holds`, `_variant_holds` and the helpers they read move out of `_serialize`, which imports construction, into a module construction and the dump both import (below), and one predicate answers "is this value one of that type?" for both directions.
A reference cannot read inside an instance a caller's data holds: it refuses with `cannot traverse into Model` rather than reading a wrong value, so `${a.b}` == built `a.b` is never broken silently; that goes in limitations, and the question of traversing a built object is [FEAT-35](../features/FEAT-35-expressions-read-call-results.md)'s, which meets it for a call's value.

An unsupported leaf takes an instance because a recorded decision says it does: `{call: threading.Lock}` and a `default_factory` still give a field a fresh lock ([a class taking nothing that holds C storage is no struct](../../architecture/design-decisions/a-structs-members-are-its-constructors-parameters.md#a-class-taking-nothing-that-holds-c-storage-is-no-struct), BUG-268).
The type stays refused both ways for anything read from text or written by `dump()` ([an unsupported leaf is refused both ways](../../architecture/types/serialization.md#an-unsupported-leaf-is-refused-both-ways)); a value that builds and does not dump already exists in the default factory's lock, and `{call: threading.Lock}` is its configuration-side twin.

Rejected:

- **Gate the rule to a call's value**, a flag threaded through every `_construct_*` function or a `ContextVar` set by `resolve_typed_call`: state construction has nowhere else, and the same `Model(1)` would build or not depending on whether a function or the caller's dict carried it.
- **`isinstance` alone at a struct node**: `Box('s')` under `Box[int]` would stay unchecked, part of the bug.
- **Revalidate every field of an instance** (pydantic's `revalidate_instances='always'`, off by default): it reads state off arbitrary objects, and refuses every class whose state does not mirror its constructor, the plain classes `dump()` refuses.
- **`isinstance` at every node, leaves included**: `True` under `int`, a `datetime` under `date` and a `StrEnum` member under `str` would be kept as they are, against the recorded rules that refuse or read them.
- **An unsupported leaf refused both ways, the `call:` route closed**: it removes the route BUG-268 records, for an asymmetry its default factory already has.
- **Read an unrelated instance by its attributes** (pydantic's `from_attributes=True`, off by default in pydantic and msgspec): `Other(3)` would silently become `Model(3)`, and a `Model` field would take any object with an `x`, against [class names the type it builds](../../architecture/design-decisions/class-names-the-type-it-builds.md) and [no implicit subclass inference](../../architecture/design-decisions/no-implicit-subclass-inference.md).

Precedent (run): pydantic's `model_validate` and msgspec's `convert` take an instance anywhere in the Python data; OmegaConf refuses an object in a configuration unless `allow_objects` is set.

### A tuple reads where a list reads

A list-kind node (`list[int]`, `Sequence[int]`, a `list` subclass) reads a tuple as the sequence it spells and builds its list, as a tuple node already reads a list and a set node a tuple ([FEAT-60](../features/FEAT-60-a-tuple-reads-where-a-list-reads.md)).
A set stays refused under a list: it has no positions, and its order varies from run to run for strings, so the dump would not be reproducible.

| | today (run) | chosen |
|---|---|---|
| `seq: Sequence[int]`, call returns `(1, 2)` | `(1, 2)`, through `_accepts` | `[1, 2]`, what a file builds for the field |
| `xs: list[int]`, call returns `(1, 2)` | refused | `[1, 2]` |
| `build(F, {"seq": (1, 2)})` | refused | `[1, 2]` |
| `xs: list[int]`, call returns `{1, 2}` | refused | refused |

Without it, construction would refuse what `_accepts` takes today under `Sequence[int]`, so FEAT-60 lands before BUG-293.

Rejected: **a tuple taken only where the annotation holds one, and kept a tuple** (pydantic): a second, type-checker-shaped reading inside construction, which reads `Sequence` as `list` everywhere else ([a builtin's subclass is that builtin](../../architecture/design-decisions/a-builtins-subclass-is-that-builtin.md)); **list nodes reading a list only**, a regression for a call returning a tuple under `Sequence[int]`; **sets too** (pydantic lax, msgspec, cattrs), for the reproducibility above.

Precedent (run): `list[int]` given `(1, 2)` is `[1, 2]` in pydantic lax, msgspec and cattrs, refused in pydantic strict; `Sequence[int]` given `(1, 2)` is `[1, 2]` in msgspec, kept a tuple in pydantic and cattrs.

### A call's value is configuration written in its place, on every node

A dict or a list in a call's value is read as the same value written in the configuration where the `call:` stands: a tag selects a class, a nested opener is read, a cast pin is read.
That is what a typed field does today; it now holds on every node, an `Any` and a Callable included ([FEAT-61](../features/FEAT-61-a-calls-value-is-configuration-on-an-any-and-a-callable-node.md)).

| `build(…)` | today (run) | chosen |
|---|---|---|
| `m: Model`, call returns `{'class': 'pkg.Sub', 'x': 1}` | `Sub(x=1)` | `Sub(x=1)` |
| `n: int`, call returns `{'call': 'pkg.nine'}` | `9` | `9` |
| `n: int`, call returns `{'__cast__': 'int', '__value__': '5'}` | `5` | `5` |
| `a: Any`, call returns `{'call': 'pkg.nine'}` | `{'call': 'pkg.nine'}` | `9`: an `Any` node reads every opener |
| `a: Any`, call returns `'pkg.nine'` | `'pkg.nine'` | `'pkg.nine'`: a bare string under `Any` stays text |
| `f: Callable[[int], int]`, call returns `'pkg.inc'` | `returned 'str', which is not callable` | `inc`, read as a Callable's path, its signature checked |
| `f: Callable[[int], int]`, call returns `{'bind': 'pkg.inc'}` | `returned 'dict', which is not callable` | `inc` |

`build(G, json.load(untrusted))` already runs any `call:` the data holds, so a function returning untrusted data adds no new kind of risk: its value is trusted as a configuration file is.
It amends one recorded sentence, in [an `Any` node reads every opener](../../architecture/design-decisions/an-any-node-reads-every-opener.md): "`call:` takes its target's value as it is" becomes "takes its target's value as configuration written in its place"; its rationale and rejected alternatives argue for reading openers rather than keeping them as data, and none for "as it is", which mirrored `_accepts(Any, …)` answering `True`.
Its recorded cost already points this way: a dict a program puts in an `Any` with an opener key reads back as the spec it spells.

Rejected:

- **A call's value is data** (Hydra, which never instantiates a target's return value again): no tag, opener or pin read in it.
  It needs a data mode threaded through construction (the tag, `_is_typed_call`, the pin, `_construct_any`), the same dict would build or not depending on who carried it, and `m: {call: tagged}` stops building.
- **Today's split**, typed fields reading it and `Any` keeping it: one exception to explain, which existed only because `_accepts(Any, …)` answered first.
- **A Callable's call value must already be callable**: the Callable kind would be the one node where a call's value is not configuration.

### A call's value is bounded where it enters

A call's value is a new entry point for data, so `_depth.refuse_overflow` checks it where it lands, counted from the node's own depth, as it checks `build()` data ([a configuration nests at most 64 levels](../../architecture/design-decisions/a-configuration-nests-at-most-64-levels.md#where-it-is-counted)): a value holding itself, nesting past 64 levels or copying past 100 000 positions is refused with the message `build()` data gets ([BUG-297](../bugs/BUG-297-a-call-whose-value-is-the-same-call-or-holds-itself-recurses-raw.md)).
A chain of calls at one node — a call whose value is another `call:` at the same position — does not deepen the position, so it is bounded on its own: a spec equal (`==`, the raw spec being configuration data) to one already made at that node is refused as a cycle naming its targets, and a chain that never repeats is refused once its links and the node's depth pass 64, each link a level, since each costs construction a recursion.

```python
def loop():
    return {"call": "pkg.loop"}  # the same spec again


def count(i=0):
    return 5 if i == 3 else {"call": "pkg.count", "args": {"i": i + 1}}


def forever(i=0):
    return {"call": "pkg.forever", "args": {"i": i + 1}}
```

| `n: int` | today (run for `loop`) | chosen |
|---|---|---|
| `{call: pkg.loop}` | raw `RecursionError` | refused: the call at `n` returns `{call: pkg.loop}`, a call already made there, so it never ends |
| `{call: pkg.count}` | `5` | `5` |
| `{call: pkg.forever}` | raw `RecursionError` | refused once the chain passes 64 levels, naming its first and last targets |
| a recursive `Node`, call returns a dict holding itself | raw `RecursionError` | `'node.child' holds 'node', a value that contains itself` |

A self-holding value a typed field took "as it is" today, a `list[Any]` given a list holding itself, is refused from BUG-297 on: construction would recurse through it once BUG-293 lands, and a value holding itself is refused wherever it enters.

Rejected: **the depth bound alone**, which stops `loop` at 65 levels and names the symptom, against the recorded reasoning that a cycle is refused as one ([a value that holds itself](../../architecture/design-decisions/a-configuration-nests-at-most-64-levels.md#a-value-that-holds-itself-is-refused-as-one)); **no call at the same node**, which contradicts "configuration written in its place", since a file may write `n: {call: g}`.

### `${…}` in a call's value is text

Expressions resolve before construction, and a call's value is computed during it, so a call's value is never searched for expressions: `${…}` in it is the text it is.

| `build(…)` | chosen |
|---|---|
| `greeting: str`, call returns `'Hello ${name}'` (text for `string.Template`) | `'Hello ${name}'` |
| `n: int`, call returns `'${n}'` | refused: `Cannot coerce str '${n}' to int` |

That is today's behavior, made the rule: a function's text is data, as a channel's decoded value is ([a decoded value is data](../../architecture/design-decisions/a-decoded-value-is-data.md)).
The asymmetry with `build()` data, where `${…}` resolves, goes in limitations and to [FEAT-35](../features/FEAT-35-expressions-read-call-results.md), whose note already leaves open whether a call result is typed or raw in the expression namespace.

Rejected: **refused until FEAT-35**, which breaks legitimate template or shell text (`${HOME}`); **resolved**, which needs FEAT-35's graph and breaks the same text.

## Where it lives

- **The holding predicate** — `_holds`, `_variant_holds`, `_holds_members`, `_holds_widened`, `_abstractly_holds`, `_find_variant_type` and `_literal_holds` from `_serialize`, and `_holds_anything` from `typedload._construct` — moves to a new module, `src/confarg/typedload/_holding.py`, importing `_types` and `typedload._coerce` (which holds `_type_kind`); `typedload._construct` and `_serialize` both import it.
  It stays the [canonical decision-maker](../../architecture/invariants.md#delegate-to-the-canonical-function) for "is this value one of that type?", and FEAT-57's `instance_conforms` goes into its STRUCT branch, once ([the Protocol plan](protocol-typed-fields.md#where-it-lives)).
  `_holds_members` gains a form that returns the first member that does not hold, for the refusal's message; members are walked in declaration order.
- **A struct node** (`typedload._construct._construct_struct_dispatch`): a value that is no dict is taken when `_holds` holds it, before the tag and the subclass dispatch are asked, and refused otherwise with a message naming its class and the declared type, through a new `TypeCoercionError` factory ([messages live on exceptions](../../architecture/design-decisions/messages-live-on-exceptions.md)); a generic struct's refusal names the member.
- **An unsupported leaf** (`typedload._coerce._coerce_leaf`, where `Unsupported leaf type` is raised): an instance of the class is returned as it is.
- **A union** (`typedload._construct._construct_union`): a value that is no dict, list or tuple and that a struct or unsupported-leaf variant holds is taken by the first variant `_find_variant_type` names, before the leaf walk; a built instance takes no part in structural matching, the tag demand ([BUG-295](../bugs/BUG-295-a-union-offers-an-untagged-value-to-a-variant-that-demands-its-tag.md)'s `_demands_tag`) included, since its class answers what the tag would.
- **A list-kind node** (`_construct_collection`, `_build_items`, and the union's sequence routing, `_try_coll_variants` and `_try_fixed_seq_variants`): a tuple reads as a list (FEAT-60).
- **A call's value** has one owner, a helper in `_callable` that calls the target, bounds the chain, checks the value with `refuse_overflow` and hands it to construction: `resolve_typed_call` from BUG-297, `_resolve_call_spec` (a Callable) and `resolve_held_spec`'s `call` branch (an `Any`) from FEAT-61.
  `_accepts` is deleted with BUG-293.

## Phases

1. **[BUG-297](../bugs/BUG-297-a-call-whose-value-is-the-same-call-or-holds-itself-recurses-raw.md)**: the call-value helper on `resolve_typed_call`, with `refuse_overflow`, the cycle and the chain bound; test-first, both reproductions.
   `_accepts` still answers at its end.
2. **[FEAT-60](../features/FEAT-60-a-tuple-reads-where-a-list-reads.md)**: a tuple read where a list is, in construction and in the union's sequence routing.
3. **[BUG-293](../bugs/BUG-293-a-call-result-is-taken-unchecked-when-its-outer-class-matches.md)**, in this order, each step green before the next:
   1. Move the holding predicate to `typedload/_holding.py`, with no change in behavior.
   2. A struct node, a union and an unsupported leaf take a built instance; the refusal messages.
      `build()` data starts taking an instance here.
   3. `resolve_typed_call` hands every value to construction; `_accepts` deleted.
      Test-first: the ticket's reproduction, then the tables above.
4. **[FEAT-61](../features/FEAT-61-a-calls-value-is-configuration-on-an-any-and-a-callable-node.md)**: `_resolve_call_spec` and `resolve_held_spec`'s `call` branch through the helper, so an `Any` and a Callable read a call's value as configuration; the recorded sentence amended.

[FEAT-57](../features/FEAT-57-protocol-typed-fields.md) waits for BUG-293: its third step writes `instance_conforms` into the predicate step 3.1 moves, and from 3.2 on that predicate is asked by construction too, so a built instance under a non-runtime-checkable Protocol field raises the raw `TypeError` there until FEAT-57's third step, as the dump does today.

## Verification

Each row of the tables above becomes a test against the `loader` fixture where a channel can spell it ([testing](../../architecture/testing.md)): a `call:` is spelled by a file, the environment and argv (`--n.call pkg.f --n.args.x 4`), so every row with a `call:` runs through all five front-ends; the `build()` and `from_dict()` rows are vanilla-only, no channel spelling an object.

- The BUG-293 reproduction: `t` refused at 3 items for 2 positions, `xs` refused at `xs[0]`.
- `[Model(1), {'x': 2}]` under `list[Model]` builds both; under `list[Model]` where `Model` has a subclass, the dict needs its tag and the instance does not.
- `Box('s')` under `Box[int]` refused, naming `box.item`; `Box(1)` taken as the same object.
- `Sub(4)` under `Model` taken as the same object, also when `Model` has several subclasses.
- `Model(7)` under `Model | int` taken; `Other(3)` under `Model | int` refused with the union's message; `Other(3)` under `Model` refused naming both classes.
- `build(D, {"a": Model(1)})` and `from_dict` build; with `${a.x}` beside it, the reference refusal is unchanged.
- `{call: threading.Lock}` on 3.13+ gives a lock, `build(L, {"lock": threading.Lock()})` too, and `dump()` still refuses both.
- `True` under `int`, a `datetime` under `date` refused; `[1, 2]` under `list[float]` is `[1.0, 2.0]`; a `StrEnum` member under `str` is its text — each from a `call:`, matching `from_dict` with the same value.
- The `call:` value of a container is a new container holding the same item objects.
- A tuple under `list[int]`, `Sequence[int]`, `list[int] | int` and `list[Model]` (items read), from `build()` data and from a `call:`; a set under `list[int]` refused.
- The chain table: `loop` refused as a cycle naming `pkg.loop`, `count` gives `5`, `forever` refused past 64 with its targets, a self-holding value refused naming both positions, under a typed field and, from FEAT-61, under `Any` and a Callable.
- A call's value nested 60 levels below a node 10 deep is refused at 64, counted from the root.
- `'Hello ${name}'` from a call under `str` is the text; `'${n}'` under `int` is refused as text.
- From FEAT-61: the `Any` and Callable rows above; a bare dotted string under `Any` stays text; a Callable's path value whose signature does not fit is refused by the signature check.
- `dump()` of each built value reads back, the instance-holding ones included.

## What moves to the architecture notes when it lands

- A design decision, "a call's value is read by construction", carrying the first, second and fourth sections above with their rejected alternatives and precedents.
- [callables § call in a typed field](../../architecture/callables.md#call-in-a-typed-field): "a value the annotation already accepts is taken as it is" becomes "the value is read by construction, as `build()` data is; a built instance of what a node names is taken as it is"; [§ an `Any` node reads every opener](../../architecture/callables.md#an-any-node-reads-every-opener) and the decision of that name amended (FEAT-61); [§ call computes a value](../../architecture/callables.md#call-computes-a-value), a Callable's call value read as a Callable spec.
- [types/construction](../../architecture/types/construction.md): a built instance at a struct node, a union and an unsupported leaf; a tuple at a list-kind node.
- [a configuration nests at most 64 levels § where it is counted](../../architecture/design-decisions/a-configuration-nests-at-most-64-levels.md#where-it-is-counted): a call's value, among the places a value enters; the chain bound and its cycle.
- [types/serialization](../../architecture/types/serialization.md): `_holds` lives in `typedload/_holding.py`, asked by construction too.
- [invariants](../../architecture/invariants.md): a decision-maker row, "is this value one of that type?" → `typedload._holding._holds`.
- [limitations](../../architecture/limitations.md): a reference cannot read inside a built instance in a caller's data; `${…}` in a call's value is text, where it resolves in `build()` data; a call's value is trusted as a configuration file is; a struct instance is taken without its non-generic fields being checked; a container a call returns is copied, its items shared.
- User documentation: the README's `call:` section, on what a function may return.

## Related, not part of this plan

- [FEAT-35](../features/FEAT-35-expressions-read-call-results.md): an expression reading a call result meets a built instance, and whether `${…}` in a call's value stays text once calls join the graph.
- [FEAT-39](../features/FEAT-39-a-struct-instance-default-is-no-base.md): an instance default laid as a base layer; this plan takes an instance in data, it lays none.
- [BUG-288](../bugs/BUG-288-an-ambiguity-inside-a-union-variant-lets-the-next-variant-take-the-value.md): a union's walk past an ambiguous variant, which a built instance never enters.
