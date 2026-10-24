# The object dump writes state

The dumps serialize different things, for different uses (maintainer-chosen):

| | Writes | For |
|---|---|---|
| `dump_file(merge(...))` | the configuration **as written**: every `${...}`, every `call:`, `class:`, `bind:` and `classfn:` spec, kept verbatim | understanding what was passed to the program, and reusing it: its dependency logic is all there. It does not replay: a `call:` reruns whatever its target does by then |
| `dump_file(resolve(...))` | the configuration with its expressions **resolved** | replaying a run; relaunching with other settings is not its use, since the dependencies between values are gone. Today it still keeps each `call:` as written and leaves out every default nothing touched, which FEAT-48 is for |
| `dump(obj)`, `dump_file(obj)` | the **state** of the built object: the values the program ran with | forensics: how the inputs were interpreted and what the program effectively used, changes made after `build()` included |

So an object dump holds no `${...}` and no `call:`.
A `call:` result is dumped as what it produced, as any other value of its type would be: on a typed field, the value it built; on a Callable field, the callable it returned, through the callable rules ([callables](../callables.md#round-trip)).
A value that no configuration spells, such as a closure or a lambda a factory returned, cannot be dumped from the object, and the merged dict is where its `call:` survives.

Why: a dump that holds a `call:` re-runs the function when it is read back, and so reproduces whatever the function returns *then*.
If the function changed in between, nothing in the dump leads back to the values that were used, and recording them is the whole point of dumping the object.
The rule is the one plain classes already follow: confarg reads the attributes, it does not replay the constructor call ([limitations](../limitations.md#callables-and-serialization)).

A reference to code is still state: a function, a class or a `type[X]` value is dumped as its dotted path, since naming that code is all a field holding it holds.
The arguments a `bind:` partial holds are dumped as values, and a callable instance or a bound method's owner as the fields it holds ([callables](../callables.md#an-object-dumps-the-state-it-holds)), never as the spec it was built from.

Rejected:

- **Stamp a typed `call:` result with its spec and dump the spec** (FEAT-33, declined).
  A value that takes an attribute would have dumped as the call, and one that does not, an `int`, a `tuple` or a frozen dataclass, as its value.
  The dump would then re-run the function on read-back.
  It would also have lost any change made to the value after `build()`, and an object a factory shares with other configurations would have carried the spec of whichever configuration stamped it last.
  A Callable field's `call:` result was stamped this way from the initial version, until BUG-191 dropped the stamp: a factory that returns a module function shared it with every configuration naming that function.
- **Dump the stamp only while it still describes the value**, by re-running the call at dump time or by comparing with a snapshot taken at build time.
  That fixes the stale spec, but the dump still holds a call whose result depends on the code that runs at reload.

## The object dump is forensic

`dump(obj)` writes what the object holds, as far as it can read it; reading it back is not its goal, since the object does not know the arguments it was built from.
Where the state mirrors the constructor's parameters it round-trips, and that remains worth keeping where it is possible; where it does not, a dump that does not load back as it stands is the price of recording the state.

### A dataclass dumps the fields it stores

A dataclass is written as `dataclasses.fields()`, its declared state (`_types._struct_state_fields`), not as its members ([a struct's members are its constructor's parameters](a-structs-members-are-its-constructors-parameters.md#a-structs-members-are-its-constructors-parameters)).
So an `init=False` field is written, though no channel sets it, and an `InitVar` never is, though every channel does: `Derived(n=2)` dumps as `{n: 2, derived: 20}`, which reloads as `Unknown field(s) ['derived']`, and `Seeded(seed=5)` as `{n: 6}`.
Writing `seed` would be wrong as well as impossible: the object stores no `seed`, and its effect is already in `n`, so `Seeded(n=6, seed=5)` would build `n=11`.
A `HandInit(7)` dumps its fields, `{a: 5, b: 2}`, which no channel sets either.

Rejected: writing the members instead, `{n: 2}` for `Derived`, which reloads, but records a computed value only by recomputing it, and cannot write `HandInit`'s `total` or `Seeded`'s `seed` at all.
Also rejected: writing `fields()` and having every loader check an `init=False` key against the value construction computes, which keeps such a dump loadable but makes `--derived.derived` a flag that only checks.

### A plain class dumps the parameters it holds

A plain class declares no state but its constructor, so it is written as its constructor's parameters, each read from the attribute of the same name (`_serialize._held_attribute`).
An instance attribute, a slot, a property and what `__getattr__` answers count as held; a plain class attribute does not, since it is the class's value, not the instance's: `class P: seed = 0` with an `__init__(self, n, seed)` that never stores `seed` is refused rather than written as `seed: 0`, the value nobody passed.
A parameter the instance does not hold is refused, naming `dump_file(merge(...))` as what keeps the arguments as given.

Rejected: the public instance attributes (`vars()`), the plain-class equivalent of `fields()`, which walks the implementation rather than the configuration: a `logging.Logger` would write its `parent`, `manager` and `handlers`, a cycle through `manager.loggerDict` among them, where its parameters write `{class: logging.Logger, name: app, level: 0}`; and every class holding a lock or a socket would reach the writer with it.
Also rejected: the class-body annotations when there are some, the parameters otherwise, which reads two declarations for one kind; and leaving a parameter the instance does not hold out of the dump, which turns a refusal into a dump that is incomplete with no sign of it.
Correct serialization of a custom class is its author's to provide: registering how a class dumps is FEAT-49.

Before this, `dump()` refused a plain-class root, though a plain class in a field dumped by the same rule; no note recorded why, and the root now dumps as a field does.

Precedents: pydantic's `model_dump` and cattrs' `unstructure` serialize the state of an object.
Every dataclass-based library run against `Seeded(seed=5)` — stdlib `asdict()`, pydantic, cattrs, msgspec — writes `{n: 6}`, and none of them reads it back when the `InitVar` has no default.
cattrs alone leaves an `init=False` field out; `asdict()`, pydantic and msgspec write it, and their loaders drop it silently on the way back in, which a loader refusing unknown keys cannot do.
Hydra (OmegaConf with `_target_`) and jsonargparse (`class_path`) save the configuration and never serialize the instantiated object back. confarg keeps its dumps apart, and does not let one stand in for another.

Cost: a configuration whose `call:` returns something that has no configuration spelling can be saved only from the merged dict.
A value changed after `build()` is saved only from the object.
An object whose state does not mirror its constructor, a dataclass with an `init=False` field or a required `InitVar`, dumps as a file that does not load back as it stands ([limitations](../limitations.md#callables-and-serialization)).
