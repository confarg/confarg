# The object dump writes state

The two dumps serialize two different things, for two different uses:

| | Writes | For |
|---|---|---|
| `dump_file(merge(...))` | the configuration **as written**: every `${...}`, every `call:`, `class:`, `bind:` and `classfn:` spec, kept verbatim | saving how the values are produced, to produce them again |
| `dump(obj)`, `dump_file(obj)` | the **state** of the built object: the values the program ran with | recording which values were used, to run with them again |

So an object dump holds no `${...}` and no `call:`. A `call:` result is dumped as what it
produced, as any other value of its type would be: on a typed field, the value it built; on a
Callable field, the callable it returned, through the callable rules
([callables](../callables.md#round-trip)). A value that no configuration spells, such as a
closure or a lambda a factory returned, cannot be dumped from the object, and the merged dict
is where its `call:` survives.

Why: a dump that holds a `call:` re-runs the function when it is read back, and so reproduces
whatever the function returns *then*. If the function changed in between, nothing in the dump
leads back to the values that were used, and recording them is the whole point of dumping the
object. The rule is the one plain classes already follow: confarg reads the attributes, it does
not replay the constructor call ([limitations](../limitations.md#callables-and-serialization)).

A reference to code is still state: a function, a class or a `type[X]` value is dumped as its
dotted path, since naming that code is all a field holding it holds. The arguments a `bind:`
partial holds are dumped as values. `class:` instances and `classfn:` owners still dump the
arguments they were built with, not the values they hold after `build()`
([limitations](../limitations.md#callables-and-serialization)).

Rejected:

- **Stamp a typed `call:` result with its spec and dump the spec** (FEAT-33, declined). A
  value that takes an attribute would have dumped as the call, and one that does not, an
  `int`, a `tuple` or a frozen dataclass, as its value. The dump would then re-run the
  function on read-back. It would also have lost any change made to the value after
  `build()`, and an object a factory shares with other configurations would have carried the
  spec of whichever configuration stamped it last. A Callable field's `call:` result was stamped this way from the initial version, until BUG-191 dropped the stamp: a factory that returns a module function shared it with every configuration naming that function.
- **Dump the stamp only while it still describes the value**, by re-running the call at dump
  time or by comparing with a snapshot taken at build time. That fixes the stale spec, but the
  dump still holds a call whose result depends on the code that runs at reload.

Precedents: pydantic's `model_dump` and cattrs' `unstructure` serialize the state of an object.
Hydra (OmegaConf with `_target_`) and jsonargparse (`class_path`) save the configuration and
never serialize the instantiated object back. confarg keeps both as two dumps, and does not
let one stand in for the other.

Cost: a configuration whose `call:` returns something that has no configuration spelling can be
saved only from the merged dict. A value changed after `build()` is saved only from the object.
