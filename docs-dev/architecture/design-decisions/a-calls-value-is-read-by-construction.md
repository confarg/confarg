# A call's value is read by construction

Every value a `call:` computes on a typed field, or on an `Any`, is handed to construction, which reads it as it reads a dict a caller passes to `build()` or `from_dict()`: containers are rebuilt item by item, each item coerced or refused at its own position, a union ranked as any union is (BUG-293).
Nothing takes a value "as it is" before construction has looked at it.

`_callable._accepts`, which did, asked `isinstance` of the annotation's origin alone, so a value whose outer class matched was taken unchecked at every depth below it, and it disagreed with the dump's answer to the same question, `_holds`: `_accepts(tuple[int, int], (1, 2, 3))` was `True` where `_holds` is `False`, `_accepts(float, 1)` `False` where `_holds` is `True`.

| a `call:` on | returns | before | now |
|---|---|---|---|
| `ms: list[Model]` | `[Model(1), {'x': 2}]` | `[Model(1), {'x': 2}]`, silently | `[Model(1), Model(2)]` |
| `fs: list[float]` | `[1, 2]` | `[1, 2]` | `[1.0, 2.0]`, as [a float reads an int as its digits](a-float-reads-an-int-as-its-digits.md) reads a native int |
| `n: int` | `True` | `True` | refused, as `from_dict({"n": True})` is |
| `t: tuple[int, int]` | `(1, 2, 3)` | `(1, 2, 3)`, silently | refused: `expected 2 elements, got 3` |
| `xs: list[int]` | `['a', 'b']` | `['a', 'b']`, silently | refused at `xs[0]` |
| `seq: Sequence[int]` | `(1, 2)` | `(1, 2)` | `[1, 2]`, what a file builds for the field ([a tuple reads where a list reads](../types/construction.md#a-tuple-reads-where-a-list-reads)) |
| `ms: list[Model]` | the module-level list `SHARED` | `SHARED` itself | a new list holding the same `Model` objects |

The leaf rows follow rules already recorded for a Python value: a `datetime` under `date` is refused ([the date and time types](the-date-and-time-types-are-built-in-leaves.md) rejected the subclass rule), a `StrEnum` member under `str` reads as its text, a `Port(int)` stays a `Port`.

Rejected:

- **A deep hold, else construct**: take the value unchanged when it holds at every depth as a type checker reads it, otherwise construct all of it.
  A mixed `[Model(1), {'x': 2}]` would be refused (`expected dict, got Model` at `ms[0]`), and the predicate could not be `_holds`: `_holds(float, 1)` is `True`, so a top-level `1` under `float`, which construction turned into `1.0`, would stay an int.
  It also walks the value twice, once to check and once to build.
- **A top-level struct instance only**: take an instance of the struct the annotation names, construct every other value, with no instance taken below.
  `list[Model]` given `[Model(1)]`, the commonest shape of a factory's value, would have started failing.

Precedent (run): pydantic, lax and strict, and msgspec's `convert` rebuild containers, take a model instance as it is (pydantic's `revalidate_instances='never'`, its default), turn `[1, 2]` under `list[float]` into `[1.0, 2.0]` and return a new list; msgspec and pydantic's strict mode refuse `True` as an `int`.
cattrs refuses the mixed list.

## Construction takes a built instance of what its node names

A node takes a value that is already what it names, as it is, through the reading its kind already has ([construction](../types/construction.md#a-built-instance-is-taken-as-it-is)):

| node | takes as it is | by |
|---|---|---|
| a struct (`Model`, a plain class) | an instance of the class or of a subclass; for a generic struct, one whose members hold their bound types | `_holds`, the dump's predicate |
| a leaf with a coercion (built-in or registered) | what the coercion already takes as it is | the coercion, unchanged: `True` under `int` and a `datetime` under `date` stay refused |
| an unsupported leaf (`threading.Lock` on 3.13+, `complex`, an unregistered `re.Pattern`) | an instance of the class | `_holds`, whose answer for such a leaf is `isinstance`, the only reading the kind has |
| a namedtuple, a tuple, a set, a Callable, a `type[X]` | unchanged: each already reads a built value | — |

The rule is not gated: a struct instance in `build()` or `from_dict()` data is taken too, where it was refused.
The merge never meets one, since a file, a variable and a flag cannot spell one, so only a caller's own data and a call's value carry one.

| `build(…)` | before | now |
|---|---|---|
| `m: Model`, call returns `Sub(4)` | `Sub(4)` | `Sub(4)`: an instance needs no tag, its class is the tag's answer |
| `box: Box[int]`, call returns `Box('s')` | `Box('s')`, silently | refused, naming the member: `it holds 's' at 'box.item', which is no int` |
| `m: Model`, call returns `Model(x='a')` | `Model(x='a')` | `Model(x='a')`: a non-generic class's constructor is its own contract |
| `build(D, {"a": Model(1)})` | `expected dict, got Model` | `D(a=Model(x=1))` |
| `build(D, {"a": Model(1), "n": "${a.x}"})` | `MissingReferenceError: … cannot traverse into Model` | the same refusal |
| `lock: threading.Lock`, `{call: threading.Lock}` | a fresh lock | a fresh lock |
| `m: Model`, call returns `Other(3)` | `expected dict, got Other Other(x=3)` | refused: `got Other Other(x=3), which is no Model; a Model, or a dict of its fields, builds one` |

So `_holds` answers "is this value one of that type?" for both directions, construction and the dump, from `typedload._holding`, which both import.
A reference cannot read inside an instance a caller's data holds: it refuses with `cannot traverse into Model` rather than reading a wrong value, so `${a.b}` == built `a.b` is never broken silently ([limitations](../limitations.md#callables-and-serialization)); reading a built object is [FEAT-35](../../todo/features/FEAT-35-expressions-read-call-results.md)'s question, which meets it for a call's value.

An unsupported leaf takes an instance because a recorded decision says it does: `{call: threading.Lock}` and a `default_factory` give a field a fresh lock ([a class taking nothing that holds C storage is no struct](a-structs-members-are-its-constructors-parameters.md#a-class-taking-nothing-that-holds-c-storage-is-no-struct), BUG-268).
The type stays refused both ways for anything read from text or written by `dump()` ([an unsupported leaf is refused both ways](../types/serialization.md#an-unsupported-leaf-is-refused-both-ways)); a value that builds and does not dump already existed in the default factory's lock, and `{call: threading.Lock}` is its configuration-side twin.

Rejected:

- **Gate the rule to a call's value**, a flag threaded through every `_construct_*` function or a `ContextVar` set by `resolve_typed_call`: state construction has nowhere else, and the same `Model(1)` would build or not depending on whether a function or the caller's dict carried it.
- **`isinstance` alone at a struct node**: `Box('s')` under `Box[int]` would stay unchecked, part of the bug.
- **Revalidate every field of an instance** (pydantic's `revalidate_instances='always'`, off by default): it reads state off arbitrary objects, and refuses every class whose state does not mirror its constructor, the plain classes `dump()` refuses.
- **`isinstance` at every node, leaves included**: `True` under `int`, a `datetime` under `date` and a `StrEnum` member under `str` would be kept as they are, against the recorded rules that refuse or read them.
- **An unsupported leaf refused both ways, the `call:` route closed**: it removes the route BUG-268 records, for an asymmetry its default factory already has.
- **Read an unrelated instance by its attributes** (pydantic's `from_attributes=True`, off by default in pydantic and msgspec): `Other(3)` would silently become `Model(3)`, and a `Model` field would take any object with an `x`, against [class names the type it builds](class-names-the-type-it-builds.md) and [no implicit subclass inference](no-implicit-subclass-inference.md).

Precedent (run): pydantic's `model_validate` and msgspec's `convert` take an instance anywhere in the Python data; OmegaConf refuses an object in a configuration unless `allow_objects` is set.

## A call's value is configuration written in its place

A dict or a list in a call's value is read as the same value written in the configuration where the `call:` stands: a tag selects a class, a nested opener is read, a cast pin is read, on a typed field and on an `Any` alike.

| `build(…)` | before | now |
|---|---|---|
| `m: Model`, call returns `{'class': 'pkg.Sub', 'x': 1}` | `Sub(x=1)` | `Sub(x=1)` |
| `n: int`, call returns `{'call': 'pkg.nine'}` | `9` | `9`, the chain bounded ([a chain of calls is bounded on its own](a-configuration-nests-at-most-64-levels.md#a-chain-of-calls-is-bounded-on-its-own)) |
| `n: int`, call returns `{'__cast__': 'int', '__value__': '5'}` | `5` | `5` |
| `a: Any`, call returns `{'call': 'pkg.nine'}` | `{'call': 'pkg.nine'}` | `9`: an `Any` node reads every opener |
| `a: Any`, call returns `'pkg.nine'` | `'pkg.nine'` | `'pkg.nine'`: a bare string under `Any` stays text |

`build(G, json.load(untrusted))` already runs any `call:` the data holds, so a function returning untrusted data adds no new kind of risk: its value is trusted as a configuration file is.
An `Any` node took a call's value as it was only because `_accepts(Any, …)` answered before construction; [an `Any` node reads every opener](an-any-node-reads-every-opener.md) argues for reading openers rather than keeping them as data, and its recorded cost already pointed this way: a dict a program puts in an `Any` with an opener key reads back as the spec it spells.

Rejected:

- **A call's value is data** (Hydra, which never instantiates a target's return value again): no tag, opener or pin read in it.
  It needs a data mode threaded through construction (the tag, `_is_typed_call`, the pin, `_construct_any`), the same dict would build or not depending on who carried it, and `m: {call: tagged}` stops building.
- **Today's split**, typed fields reading it and `Any` keeping it: one exception to explain, which existed only because `_accepts(Any, …)` answered first.

## `${…}` in a call's value is text

Expressions resolve before construction, and a call's value is computed during it, so a call's value is never searched for expressions: `${…}` in it is the text it is.
`greeting: str`, given `'Hello ${name}'` by a call (text for `string.Template`), is that text; `n: int` given `'${n}'` is refused, `Cannot coerce str '${n}' to int`.
A function's text is data, as a channel's decoded value is ([a decoded value is data](a-decoded-value-is-data.md)).
The asymmetry with `build()` data, where `${…}` resolves, is a [limitation](../limitations.md#callables-and-serialization).

Rejected: **refused until expressions can read a call's value** ([FEAT-35](../../todo/features/FEAT-35-expressions-read-call-results.md)), which breaks legitimate template or shell text (`${HOME}`); **resolved**, which needs FEAT-35's graph and breaks the same text.
