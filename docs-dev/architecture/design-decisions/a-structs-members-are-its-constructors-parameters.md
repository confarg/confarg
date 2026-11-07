# A struct's members are its constructor's parameters

What every channel can set on a struct, and what construction passes it, is the parameters of the call that builds it: the same answer for a dataclass and for a plain class (FEAT-14, BUG-153, maintainer-chosen).
`_types._init_params` reads them, once per class, and `_struct_fields`, `_struct_defaults`, `_struct_required` and `_struct_declared_defaults` are views of it, so the CLI walk, flag registration, the environment, files, the default layer and construction cannot disagree about a member.

Before, a plain class was read by its `__init__` signature and a dataclass by `dataclasses.fields()`, used as a proxy for the signature it differs from in both directions:

```python
@dataclass
class Derived:  # a field computed after __init__
    n: int = 1
    derived: int = field(init=False, default=0)

    def __post_init__(self):
        self.derived = self.n * 10


@dataclass
class Seeded:  # an __init__-only argument, never stored
    n: int = 1
    seed: InitVar[int] = 0

    def __post_init__(self, seed):
        self.n += seed


@dataclass(init=False)
class HandInit:  # fields a, b, but the __init__ is handwritten
    a: int
    b: int = 2

    def __init__(self, total: int):
        self.a, self.b = total - 2, 2
```

`Derived` could not build at all, since its `derived=0` default was passed to an `__init__` that does not take it, and `--derived` was a flag that could never work; `--seed` was refused as unknown; `--total` was refused and `--a` crashed in `__init__`.
Now `derived` is no member (refused as an unknown field, as `dataclasses.replace()` refuses it), `seed` is one, typed by the type the `InitVar` wraps, and `HandInit` is set through `total` alone.

## A dataclass is read by its `__init__`

A parameter that is a dataclass field, an `InitVar` included, is typed by the class's own annotation, so a forward reference resolves as it did through `fields()`; any other parameter, of a handwritten `__init__` or of an undecorated subclass's own, is typed by the constructor's annotations (`_types._member_hints`).
A `default_factory` field shows a private sentinel as its signature default; `_init_defaults` replaces it by a call of the factory, and `_struct_declared_defaults` leaves it out, as it left the factory out before.
Construction calls a dataclass through the same positional split as a plain class (`_construct._call_struct`), so a handwritten `def __init__(self, a, /)` is reached.

What the instance *stores* is another question, which `dump()` answers with `fields()` ([the object dump writes state](the-object-dump-writes-state.md#a-dataclass-dumps-the-fields-it-stores)).

An undecorated subclass that adds `__init__(self, extra, **kwargs)` and forwards `**kwargs` to its parent is read as a plain class with the same signature is: `extra` and a `kwargs` dict, so `--kwargs.n 2` where the parent's `--n 2` worked before.
That is a regression for that shape, accepted for the one rule; reading a forwarded `**kwargs` as the parent's members, as jsonargparse does by reading the source, is FEAT-50.

## A class taking nothing is a struct with no fields

A class whose constructor takes no argument — one inheriting `object.__init__`, one declaring `def __init__(self)` — is a struct with no fields, as a field-less dataclass always was: `{}` builds it, a class tag selects it, a missing field builds it from nothing, and `dump()` writes `{}`.
Before, the first read as a struct with the `args` and `kwargs` fields of `object.__init__`'s `(self, /, *args, **kwargs)`, which `build()` then refused with a raw `TypeError`, and the second as an unsupported leaf, so `{class: C}` and `{classfn: C.m}` refused a class declaring `__init__(self)` and built one declaring none.

Making both a leaf instead was rejected: a field-less dataclass would have lost what it does today, a marker variant in a union (`mode: Fast | Slow`) selected by its tag.

### A class taking nothing that holds C storage is no struct

A class taking nothing whose instances hold storage beyond their `__dict__`, `__weakref__` and slots is an unsupported leaf, not a struct with no fields (`_types._holds_c_storage`, BUG-268, maintainer-chosen): `_thread.lock`, `re.Pattern`, a `random.Random`, `threading.local` or `Exception` subclass whose `__init__` takes nothing, and any subclass of a C extension's type that takes nothing.
It is refused both ways, as `_thread.RLock` already was on every version, its signature not reading ([an unsupported leaf is refused both ways](../types/serialization.md#an-unsupported-leaf-is-refused-both-ways)): `{}` and `{class: threading.Lock}` build nothing, a `lock` field is not dumped, and a lock an `Any` node holds is written untyped with a warning, which `dump_file()` then refuses.
`{call: threading.Lock}` and a `default_factory` still give a field a fresh lock, and `register_leaf_type` makes such a class a leaf.
From 3.13 `_thread.lock` is built by a C `__new__`, so it reads no signature before this test is asked ([a class built by a C `__new__` reads no signature](#a-class-built-by-a-c-__new__-reads-no-signature)); a subclass with a Python `__init__` taking nothing still meets it.

Why: the struct-with-no-fields reading is there for a marker class, which holds nothing; a C type's own storage says the class is no marker.
What it holds no constructor parameter sets, so `{}` is all its dump could be, and `{}` builds a fresh instance: a lock's locked flag or a generator's position, which no attribute even reads, as much as an exception's `args`, which one does.
Python 3.13 made `threading.Lock` the importable class `_thread.lock`, where 3.12 had a factory function: a held lock then dumped as `{class: _thread.lock}`, and a `lock: threading.Lock` field as `{}`, both reading back as an unlocked lock, with no warning.
On 3.12 the same lock had been refused only because no dotted path named its class.

The test is the one `object.__reduce_ex__` refuses to pickle a value by, which raises `cannot pickle '_thread.lock' object`: the instance's basic size against `object`'s plus a pointer for each of a non-managed `__dict__`, a non-managed `__weakref__` and every declared slot, or any item size.
A slot a subclass declares again under its base's name counts twice, as it is stored twice: the redeclaration allocates a second pointer.
Pickle exempts a class that writes its own `__getstate__` or `__reduce__`, as `random.Random` does; confarg does not, since it reads no `__getstate__`: a drawn generator would still dump as `{}`.
The rule is limited to a class taking nothing: a C type with parameters is built from them, `random.Random(1)` from `{class: random.Random, x: 1}`, and its dump reads each one back from the attribute that holds it, refusing one it does not hold ([a plain class dumps the parameters it holds](the-object-dump-writes-state.md#a-plain-class-dumps-the-parameters-it-holds)).
A class whose state lives in its `__dict__`, such as `threading.Event`, stays a struct with no fields, and what it holds is not recorded, as it is not for any plain class ([limitations](../limitations.md#callables-and-serialization)).

Rejected:

- **Refuse at the dump only**: an object holding C storage is never the same value as the one its spec rebuilds unless it compares equal (`_serialize._same_value`).
  That warned in an `Any` node, but left `{class: threading.Lock}` building on 3.13 and later only, and the typed `lock` field writing `{}` until a second check covered it.
- **Accept it, and fix the tests**: the lock follows the rule that a plain class dumps its parameters, so a field-less one records nothing; the BUG-251 tests would have used an object no path names.
  It left the 3.13 dump silently lossy, and the two lock classes of `_thread` reading differently for want of a readable signature.

Precedents: `pickle`, `copy.deepcopy` and `dataclasses.asdict` refuse a lock; pydantic, cattrs and msgspec refuse `threading.Lock` as a type, as they refuse every plain class; jsonargparse reads it as a class (`class_path: _thread.lock`) and refuses to dump the instance.

## Which signature is read

`_types._constructor_parameters` reads `__init__` when the class does not inherit it from `object`, else `__new__` when it does not inherit that one, else nothing.
It is what `type.__call__` does: when `__init__` is `object`'s, the call's arguments are `__new__`'s, so `class P: def __new__(cls, x=0)` is a struct with `x`.
Either is read as itself, its first parameter (`self`, `cls`) dropped: `Fraction` is a struct of `numerator` and `denominator`, which it exposes as properties, so it dumps and reads back.
A `__new__` written in C is not read at all ([below](#a-class-built-by-a-c-__new__-reads-no-signature)).
A class whose signature does not read, as `zoneinfo.ZoneInfo`'s, is not a struct: an unsupported leaf, which `register_leaf_type` makes a supported one, as confarg does for `datetime.date` ([the date and time types are built-in leaves](the-date-and-time-types-are-built-in-leaves.md#the-date-and-time-types-are-built-in-leaves)).

Rejected: `inspect.signature(cls)`, for either.
It reads a metaclass `__call__` or a `__new__` before `__init__`, so a class with a forwarding `__new__(cls, *args, **kwargs)` beside `__init__(self, x)`, or any class of a metaclass defining `__call__(cls, *args, **kwargs)`, reads as `(*args, **kwargs)` on 3.12 to 3.15.
`__new__` was read that way until BUG-306, so that a C `__new__`'s text signature could be read, and a Python `__new__` under such a metaclass offered `args` and `kwargs` in place of its parameters: a file's `{x: 3}` was refused and argv's `--p.x` unknown.
A metaclass `__call__` that changes what the call takes is not followed; it is rare, where a registry or singleton metaclass forwarding everything is common, and the `__init__` branch never followed one either.
Precedent: jsonargparse 4.52 (run) reads past such a metaclass too, `--c.x 3` building both the `__new__` and the `__init__` class, where `inspect.signature` gives `(*args, **kwargs)` for each.

Also rejected: reading `__init__` alone, with an inherited `object.__init__` taking nothing, which made `P`'s `x` unreachable and every C value type (`date`, `Decimal`, `Fraction`) a struct with no fields that `dump()` wrote as `{}`; and making a class that overrides `__new__` while inheriting `object.__init__` a leaf, which left `P` and `Fraction` unusable until registered.

### A class built by a C `__new__` reads no signature

A class that inherits `object.__init__` and whose `__new__` is written in C, a builtin function, is not a struct, on every interpreter: `_types._constructor_parameters` refuses it as a signature that does not read (BUG-306, maintainer-chosen).
That covers `datetime`, `date`, `time`, `timedelta`, `Decimal`, `hashlib.blake2b`, and a Python subclass inheriting such a `__new__` (`class MyDate(date): pass`); each is a leaf, unsupported until registered.

Such a class reads only through its text signature, `__text_signature__`, which has two faults.
CPython adds one from one release to the next: `functools.partial`, `itertools.chain` and `types.GenericAlias` gained one in 3.13, and the four date and time types in 3.15, so one configuration meant two things by interpreter.
On 3.14 `{class: datetime.datetime, year: 2026, month: 1, day: 2}` was refused and `{class: confidential}` under `int | datetime | dict[str, str]` was the dict variant's entry; on 3.15 the first built a `datetime`, the second was a tag that failed to import.
And a text signature carries no annotation, so every parameter it names reads as `Any`: on 3.15 a file's `year: 2026` built, while argv's `--when.year 2026` reached `datetime` as the text `'2026'` and its raw `TypeError` escaped `load()`.

`Decimal` had a text signature on every interpreter, so a tag built it from `value` and `context` everywhere; it no longer does, which is the cost of the one rule.
`Fraction`'s `__new__` is written in Python and annotated by its source, so it is still a struct, and `UUID`'s `__init__` is Python, so a tag still opens it ([an explicit tag opts a leaf back in](an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in)).

An `__init__` written in C is still read: `inspect` reads it through the slot wrapper's generic `(self, /, *args, **kwargs)` on every interpreter, which reads as the same Python signature does, and argv and a file build the same object from it: `{class: _struct.Struct, args: ['<i']}` builds `Struct('<i')`, `{args: [boom]}` an `Exception` subclass inheriting `BaseException.__init__`.

Rejected:

- **Follow the signature**, and have the tests use a type no interpreter gives one: one configuration keeps meaning two things by interpreter, and every CPython release moves more types across the line.
- **Name the date and time types as leaves no tag opens**: it fixes the five types and leaves the drift of every other C type, and is a special case beside the rule.
- **Open the date and time types on every interpreter**, supplying the parameters 3.15 shows on the earlier ones: a copy of CPython's signatures to maintain, with no annotations to type argv's text by, and no precedent.
- **No constructor written in C read**, an `__init__` included: it refused `Struct`, `StringIO` and an `Exception` subclass, which build alike from argv and a file on every interpreter, and fixed no drift.

Precedents: jsonargparse 4.52 (run on 3.12 and 3.15) reads `datetime` and `Decimal` from text only, refusing a `class_path` with `init_args` for either on both interpreters; pydantic, cattrs and msgspec read the date types and `Decimal` as scalars and never build one from keys *(from their documentation, not run)*.

## A flag is typed by the member it sets

Flag registration types each flag by the member's own annotation, `Annotated` metadata kept (`_types._resolve_struct`, through `_member_hints`).
It used to read `get_type_hints(cls)`, the class's own annotations: a plain class has none for its parameters, so every one registered as `Any` — `--p.x ANY` in `--help`, and a `list` parameter taking one token on argparse and cyclopts where vanilla took the run — and an `InitVar` registered as the wrapper (`--seed VALUE`).
Latent since the initial version (PR-5).

## Precedents

| | `{'derived': 5}` into `Derived` | `{'seed': 5}` into `Seeded` | `HandInit` |
|---|---|---|---|
| stdlib `dataclasses.replace()` | refused: `field derived is declared with init=False` | accepted | — |
| pydantic | key dropped | accepted | `{'a': 1}` builds, bypassing `__init__` |
| cattrs | key dropped | key dropped | refused either way |
| dacite | set after `__init__` | accepted | `{'total': 7}` refused: missing `a` |
| msgspec | key dropped | refuses the class | `{'a': 1}` builds, bypassing `__init__` |
| jsonargparse | — | accepted, `--x.seed 5` | reads `__init__`, a forwarded `**kwargs` included |

pydantic, cattrs and msgspec drop the `derived` key because they ignore an unknown key by default; confarg refuses one, which puts it beside `replace()`.
jsonargparse is the closest precedent, the one library that reads every class, dataclass or not, by its `__init__` signature.
None of the serialization libraries reads a plain class at all: pydantic, cattrs and msgspec refuse a class taking nothing as an unsupported type.
