# Plan — Protocol-typed fields

**Drafted:** 2026-10-26 · **Status:** approved · **Tickets:** [BUG-293](../bugs/BUG-293-a-call-result-is-taken-unchecked-when-its-outer-class-matches.md), BUG-294 (landed), [BUG-295](../bugs/BUG-295-a-union-offers-an-untagged-value-to-a-variant-that-demands-its-tag.md), [FEAT-57](../features/FEAT-57-protocol-typed-fields.md), [FEAT-2](../features/FEAT-2-a-callback-protocol-reads-as-a-callable.md), [BUG-300](../bugs/BUG-300-a-tag-matching-variants-of-two-classes-is-refused-as-ambiguous.md) · **Amended:** 2026-10-28, BUG-294 landed: a `type[X]` value is read and dumped by one predicate, `_types._type_ref_admits`, over the bound `_type_ref_bounds` reads, a union's classes each, so FEAT-57 asks `class_conforms` there for a Protocol class of the bound; until it does, the dump of a `type[P]` raises the raw `TypeError` its read-back already raised; 2026-10-28, BUG-296 landed: the refusal of a Protocol class lives in `_construct_named`, the one constructor a tag and an opener share, so a tag under a `@runtime_checkable` Protocol meets it today; 2026-10-28, BUG-291 landed: the call-shape rule moved to the callables note, an unannotated or `Any` `*args, **kwargs` pair reading as `...`; 2026-10-28, after FEAT-59's design: members looked up in the `__mro__`, never on the metaclass, and a tag naming a class two Protocol variants admit (BUG-300); 2026-10-26, after a third review: a Protocol class refused in `construct_named_class` (BUG-296), the dump of a conforming non-struct value, the effective member map, abstract and coroutine members, `Concatenate`; after a second review: trivial inherited bodies, a tag-demanding variant left out of the untagged union match (BUG-295), the `type[X]` dump (BUG-294), `_is_callable` for FEAT-2, the non-struct conformer; and after a first review: a Protocol class refused at the tag, `_unproducible_return` and the synthetic constructor rewired, the member shapes settled, BUG-293 moved before FEAT-57's third step

A field annotated with a `typing.Protocol` has no story today, and most of what reaches one crashes with a raw `TypeError`: every site that asks "is this class one the annotation accepts?" calls `issubclass` or `isinstance`, which Python refuses for a Protocol that is not `@runtime_checkable`.
Where nothing calls them, a Protocol reads as a plain class whose fields are `typing.Protocol.__init__`'s `*args, **kwargs`.

```text
g: Greeter (not runtime-checkable), file g: {class: pkg.Structural, name: x}
  -> TypeError: Instance and class checks can only be used with @runtime_checkable protocols
g: Greeter, file g: {name: x}, no class inherits Greeter
  -> TypeCoercionError: Unknown field(s) ['name'] for Lone at 'g'. Valid fields: ['args', 'kwargs']
g: Greeter, file g: {}
  -> TypeError: Protocols cannot be instantiated
t: type[Greeter], file t: pkg.Structural
  -> TypeError: Instance and class checks can only be used with @runtime_checkable protocols
dump(C(g=Structural()))
  -> TypeError: Instance and class checks can only be used with @runtime_checkable protocols
f: CallP (only __call__), file f: pkg.double
  -> TypeCoercionError: Cannot construct CallP at 'f': expected dict, got str 'protomod.double'
```

A `@runtime_checkable` Protocol works by accident: `issubclass` checks member names only, so `{class: pkg.Structural}` builds, and so would a class whose `greet` takes a required argument the Protocol never passes.

The design was settled in one grilling session; each decision below names what it rejected and what the precedents do.
The examples use these classes:

```python
class Greeter(Protocol):
    def greet(self) -> str: ...


class Named(Protocol):
    name: str

    def greet(self) -> str: ...


@dataclass
class Nominal(Greeter):  # inherits the Protocol
    name: str = "n"

    def greet(self) -> str: ...


@dataclass
class Structural:  # matches by shape only
    name: str = "s"

    def greet(self) -> str: ...


class BadSig:  # right name, wrong call shape
    def greet(self, loud: bool) -> str: ...


class LaxSig:  # an extra optional keyword: still conforms
    def greet(self, *, other: int = 1) -> str: ...
```

## Decisions taken

### A Protocol is an abstract base its implementers are named into

A struct-like Protocol field takes its value through the union tag only: `{class: pkg.Structural, name: x}` builds `Structural(name="x")`, through `construct_named_class` as any named class does ([class names the type it builds](../../architecture/design-decisions/class-names-the-type-it-builds.md#class-names-the-type-it-builds)).
An untagged value is refused, whatever it holds and however many classes inherit the Protocol, the way an ABC with subclasses is refused today (`_construct_struct_dispatch`).
The message leads with what is certain, "`Greeter` is a Protocol: name a class implementing it with `--g.class`", spelled per channel as `MissingFieldError` spells its remedy, and offers the classes known to inherit it as examples only: `__subclasses__()` never lists a structural implementer, and lists nothing for a Protocol nobody inherits.
A tag naming a Protocol class is refused too, the field's Protocol or any sub-Protocol (`{class: pkg.Greeter}`, `{class: pkg.Loud}` under `g: Greeter`): it has every member it declares, so the conformance rule alone would accept it, and construction would then fail on `Protocols cannot be instantiated`.
That refusal is a question of buildability, not of conformance, and it is not the Protocol field's alone: under `Any` today `{class: pkg.Greeter}` is refused with `cannot be built with no arguments: Protocols cannot be instantiated. Supply the class's fields as keys beside the 'class' opener`, advice no key can follow, and `{class: pkg.Greeter, name: n}` with `Unknown field(s) ['name'] for Greeter … Valid fields: ['args', 'kwargs']` (run; BUG-296, landed).
So it lives in the one constructor every named class goes through, `typedload._construct._construct_named`, which `construct_named_class` and the tag both call, and which refuses a Protocol class before calling anything, for the tag, an `Any` node and a Callable's `class:` at once (landed with BUG-296); `_coerce_type_ref` refuses one under a `type[P]` field, since PEP 544 rules that only a concrete class is a `type[P]`.
A plain-class field never meets one: a Protocol may only inherit Protocols (`class P(Base, Protocol)` raises `Protocols can only inherit from other protocols`, run).
`class_conforms` stays a pure conformance answer.
jsonargparse 4.53 answers `Expected an instantiatable class, but protomod.Greeter is a protocol` for a `class_path` naming one, wherever it meets it.
A Protocol has no members of its own: its `__init__` is `typing`'s, and its declared attributes are what an implementer must have, not what a configuration sets.
Nothing infers an implementer from the keys given, for the reason PR-63 removed subclass inference ([no implicit subclass inference](../../architecture/design-decisions/no-implicit-subclass-inference.md#no-implicit-subclass-inference)): the candidates would be whatever happens to be imported.

A class that inherits `typing`'s synthetic constructor takes nothing, a Protocol and a plain nominal implementer without an `__init__` of its own alike (`class Impl(Greeter): def greet(self) -> str: ...`).
Today both read as the fields `{'args': list[Any], 'kwargs': dict[str, Any]}`, and `Impl(**keys)` escapes raw; worse, `Impl()` replaces `Impl.__init__` with `object.__init__` on its first call, after which the per-class cache still answers `args`/`kwargs` (run on 3.12).
So `_types._constructor_parameters` reads that constructor as `object.__init__`'s, recognized by identity with `typing._no_init_or_replace_init`: `typing.Protocol.__init__` resolves to `object.__init__` on 3.12 to 3.15, so it cannot be the key, and the private name is stable across those versions, pinned by a test on each.
Keyed on the function rather than on `is_protocol(cls)`, it covers the implementers, and both states of the class give the same answer, `{}`, so the cache cannot go stale.

A tag naming a class that implements two Protocol variants of a union (`{class: pkg.Structural}` under `Greeter | Named`) builds it: [BUG-300](../bugs/BUG-300-a-tag-matching-variants-of-two-classes-is-refused-as-ambiguous.md) tries the distinct bindings a tag selects in declaration order across variant classes, as `Box[int] | Box[str]` does today, where a tag matching variants of two classes is refused as ambiguous, nominally too (`AB(A, B)` under `A | B`).
A structural implementer binds by its defaults under each, so its bindings are one.

A custom `union_tag` spelled like a field of a nominal implementer keeps the recorded rule: the real field wins ([real field wins](../../architecture/design-decisions/real-field-wins.md)), as under an ABC.
With `union_tag="kind"` and `Kinded(RG)` declaring `kind`, `{kind: x}` builds `Kinded(kind='x')`, chosen by its fields with the shadowed-tag warning, as it does today for a `@runtime_checkable` Protocol (run); a structural implementer is unreachable under that tag, which goes in limitations beside the ABC one.
The default tag cannot collide, `class` being a keyword ([union tag defaults to class](../../architecture/design-decisions/union-tag-defaults-to-class.md)).
Rejected: **the tag always wins under a Protocol** (`_union_tag_shadowed` answering `False` for one), which makes the implementer's own field impossible to set and gives Protocols and ABCs two rules for one question.

Precedent: jsonargparse 4.53 refuses an untagged Protocol, `Expected an instantiatable class, but protomod.Greeter is a protocol`, and takes any class that implements it under `class_path`.
pydantic refuses a Protocol field outright (`PydanticSchemaGenerationError`) and, under `arbitrary_types_allowed`, only runs `isinstance`, so a non-runtime-checkable Protocol fails at schema build.

### A class conforms by its members and its methods' call shapes

`class: pkg.X` under a Protocol is accepted when `X` has every member the Protocol declares and each method can be called the way the Protocol calls it: parameter kinds, names and required-ness, the annotations ignored.
The rule is the same for every Protocol, `@runtime_checkable` or not; confarg never calls `isinstance` or `issubclass` on a Protocol.

| `g: {class: pkg.<X>}` under `Greeter` | Nominal | Structural | BadSig | LaxSig |
|---|---|---|---|---|
| chosen: names + call shape | ✓ | ✓ | refused | ✓ |

Rejected:

- **Nominal only**, what `issubclass` would answer if it could: it refuses `Structural`, which is the reason Protocols exist.
- **Member names only**, `isinstance`'s rule for a `@runtime_checkable` Protocol: `BadSig` builds and fails the first time `greet()` is called.
  It is also what the [class names a subclass](../../architecture/design-decisions/class-names-a-subclass-call-computes.md#class-names-a-subclass-call-computes) decision rules out: the annotation is the contract the rest of the program reads.
- **Names, call shape and annotations**, jsonargparse's rule (`implements_protocol`, which compares annotations by equality, a TypeVar matching anything).
  Equality refuses what a type checker accepts — a parameter widened from `list[int]` to `Sequence[int]`, a string annotation, an overload — and a false refusal leaves the user no workaround, where a false acceptance is still caught by their type checker.

Precedent: `ty` refuses `a: Greeter = BadSig()` (`Object of type BadSig is not assignable to Greeter`); jsonargparse 4.53 refuses it (`Import path __main__.BadSig does not implement protocol Greeter`) and accepts `LaxSig`.

The rule is asked of every class named under a Protocol, one that inherits it included: inheriting it only adds the type-parameter binding (below).
So a class that inherits the Protocol without implementing it is refused, and `_struct_subclasses`, which keeps only the subclasses `_tagged_struct` binds, leaves it out of the flags, the type walk and the tag's shadowing, where an ABC's scan lists every subclass.

A member a class finds only on a Protocol class in its MRO counts unless its body is trivial — `...`, `pass`, a docstring, `raise NotImplementedError`, mypy's rule for an abstract Protocol member — or it is marked `@abstractmethod`, whatever its body: ty and mypy both refuse to instantiate `class Inherits(Abs): pass` where `Abs.greet` is an abstract method with a real body (run), and `ABCMeta` refuses it at runtime too.
The body is read from the source with `ast`, as `cli._spec._get_field_docstrings` reads field docstrings; a member whose source cannot be read counts.
The rule only ever judges what a class inherits from a Protocol: a class defining a member itself conforms or not by its call shape, however the Protocol spells it, so an `@overload`ed Protocol method, whose bound `def` is the trivial stub after the overloads, refuses only a nominal implementer that leaves it unimplemented.

```python
class WithDefault(Protocol):
    def greet(self) -> str:
        return "hi"  # a default implementation


class Partial(Greeter):  # inherits Greeter's stub
    pass


class Inherits(WithDefault):  # inherits the default
    pass
```

| | Partial | Inherits |
|---|---|---|
| ty, mypy (run) | `Cannot instantiate abstract class` | ✓ |
| at runtime | `Partial().greet()` is `None` | `'hi'` |
| chosen: trivial bodies do not count | refused | ✓ |

confarg instantiates the class itself, so no type checker ever sees the `Partial()` call: accepting it would build a value whose method silently returns `None`.
Rejected: **counting it**, the runtime view, for that reason; **never counting a member found on a Protocol class**, which refuses `Inherits`; **excluding only `@abstractmethod` members**, which still accepts `Partial`.

A Protocol with no members — every member excluded, as `__init__` is from `__protocol_attrs__` — is satisfied by every class, as type checkers read it; only the refusal of a Protocol class applies to it.

A member is looked up in the class's `__mro__`, as an instance sees it, never on its metaclass: `inspect.getattr_static(int, "__call__")` finds `type.__call__` and `getattr_static(int, "__name__")` `type`'s attribute (run), which no instance of `int` has, so a lookup reaching the metaclass would take a class with no `__call__` for an implementer of a Protocol declaring one beside another member, and build a value that cannot be called.

Three member shapes the rule settles explicitly:

- **A method member the class provides as a non-callable** (`greet = 3`, or a `property`, read with `inspect.getattr_static`) is refused: the member must be callable before its signature is read, so the exemption for a signature `inspect` cannot read keeps covering C functions and builtins only.
- **A coroutine function where the Protocol declares a plain method, or the reverse** (`async def greet` against `def greet -> str`), passes, its call shape being the same: ty and mypy refuse both directions (run), but each turns on the declared return — a plain method annotated `-> Awaitable[str]` is implemented by an `async def` — so refusing it would read annotations; a false acceptance, recorded in limitations.
- **A method member provided only on the instance** (`self.greet = hello` in `__init__`) is refused, since methods are read on the class; the checkers split here — `ty` refuses `a: Greeter = Stored(hello)`, mypy accepts it — and confarg sides with the one that does not need an instance.
- **The expected signature is the runtime one**: for an `@overload`ed Protocol method, the last `def` of the body, its stub; the overload set is the type checker's.
  An instance method implementing a Protocol `@staticmethod` is refused because its receiver stays in its signature; type checkers refuse it too, so a later cleanup stripping receivers must keep refusing it.

### Data members are checked on the built instance

A data member — an annotation-only member, a property, any non-function member — often exists only once the instance is built, so it is checked with `hasattr` on the instance, after construction; methods are checked on the class, at the tag.

| `g: {class: pkg.<X>, ...}` under `Named` | DcAttr (`name: str` field, no default) | InitAttr (`self.name = name`) | Computed (`self.name = first.title()`) | NoAttr |
|---|---|---|---|---|
| `hasattr(cls, "name")` | False | False | False | False |
| ty | ✓ | ✓ | ✓ | refused |
| chosen: on the instance | ✓ | ✓ | ✓ | refused at `build()` |

The refusal comes at `build()`, never at `merge()`: `--g.class pkg.NoAttr` merges, as `--g.class pkg.Unrelated` under an ABC merges today.
The instance check is the one `dump()` and construction need anyway, since both ask whether a value satisfies its annotation through one predicate, `_holds`, which [BUG-293](../bugs/BUG-293-a-call-result-is-taken-unchecked-when-its-outer-class-matches.md) moves to `typedload/_holding.py` and has construction ask of every built instance, a `call:` value's included ([its plan](a-calls-value-is-read-by-construction.md#construction-takes-a-built-instance-of-what-its-node-names)).

Rejected: **ignoring data members** (jsonargparse), which accepts `NoAttr`; **checking them on the class**, through a class attribute, an annotation in the MRO or a constructor parameter, which refuses `Computed` though every type checker accepts it.

A method where a data member is declared passes `hasattr`, and is accepted: a known false acceptance, recorded in limitations.
Whether a type checker takes it turns on the member's declared type, which the rule does not read (`ty` and mypy agree, run):

| Protocol member | `name: str` | `@property name -> str` | `handler: Callable[[int], int]` | `@property handler -> Callable[[int], int]` |
|---|---|---|---|---|
| a method of that name, ty and mypy | refused | refused | refused (settable) | ✓ |
| chosen: `hasattr` | ✓ | ✓ | ✓ | ✓ |

Rejected: **refusing a method wherever a data member is declared**, which refuses the last column, valid code with no workaround; **refusing it unless the declared type is a Callable**, the only place annotations would be read, still wrong on the third column.

### One call-shape checker serves Protocol methods and `Callable[[...], R]`

The shape check landed with BUG-291, as `_conformance.call_conforms`, and its rule, its rejected alternatives and its precedents are in [callables](../../architecture/callables.md#a-callable-is-checked-by-its-call-shape): the typing specification's assignability rule for callables with the types left out, where an expected `*args, **kwargs` pair, each unannotated or `Any`, stands for `...`.
So a Protocol method declared `def greet(self, *args, **kwargs)` is implemented by any `greet`, as `ty` reads it (run), where jsonargparse refuses a `def greet(self)`; one declared `*args: int, **kwargs: int` needs both.
The expected signature of a Protocol method is read with `inspect.signature(..., eval_str=True)`, falling back to the unevaluated one when a name does not resolve, so a string `Any` reads as `Any` where it can.

What FEAT-57 adds is the expected side of a method:

- A Protocol method that is a `staticmethod` or a `classmethod` is compared without the receiver its implementation binds, as jsonargparse's `get_protocol_method_signature` does.

Rejected: **a checker per feature**, keeping the Callable one beside a new Protocol one; the two answer the same question and the existing one already drifted from the typing rules.
Precedent: jsonargparse uses one `protocol_params_match` for a Protocol's methods and for a function implementing a callback Protocol.

### A member inherited from `object` counts only where `object` declares it

`object` defines `__lt__`, `__le__`, `__gt__` and `__ge__` at runtime only to return `NotImplemented`, so `hasattr(Bare, "__lt__")` is `True` while `Bare() < Bare()` raises; typeshed's `object` declares none of the four, and `ty` refuses `lt: SupportsLT = Bare()` while accepting `eq: SupportsEq = Bare()`.
A member found only on `object` therefore satisfies a Protocol unless it is one of those four.
The list is typeshed's declaration of `object`, not a fact about Python, and the design decision cites it so: a typeshed change to `object` touches this rule.

`__protocol_attrs__` also lists `__hash__` for a Protocol that defines `__eq__`, since the class body sets `__hash__ = None`; it is a data member, so the instance check passes it whatever the implementer defines.

Rejected: **any attribute found**, `hasattr`'s answer, which takes `Bare` for `SupportsLT`.

### A callback Protocol reads as a Callable

A Protocol whose only member is `__call__` is a Callable whose expected signature is `__call__`'s without `self` ([FEAT-2](../features/FEAT-2-a-callback-protocol-reads-as-a-callable.md)): every Callable spec reaches it, and each resolved value — a function, a partial, an instance — goes through the call-shape checker.

```python
class Scorer(Protocol):
    def __call__(self, x: int, *, scale: float = 1.0) -> float: ...
```

| `f: Scorer` | value |
|---|---|
| `pkg.linear` | the function |
| `{bind: pkg.linear, args: {scale: 3}}` | `partial(linear, scale=3)` |
| `{class: pkg.Weighted, w: 3}` | the instance, which must define a conforming `__call__` |
| a bare class path `pkg.Weighted` | a factory, refused as under a Callable when `__call__`'s return annotation says its instances are not what it returns (`_unproducible_return`, which asks `class_conforms` when that annotation is a Protocol) |
| dump of a function value | its dotted path |

A Protocol with any other member beside `__call__` stays struct-like: a function has no `label`.

Two predicates move together for it, since `_KIND_ORDER` asks `STRUCT` before `CALLABLE`: `_is_plain_class` answers `False` for it, so `_is_struct_variant` does not claim it, and `_types._is_callable`, which today answers `get_origin(tp) is Callable` only, answers `True` for it; without the second, the type falls through to `LEAF`.
The expected signature has one home, `_types._expected_call_signature`, which BUG-291 made answer `(a, b, /)` for `Callable[[A, B], R]`, `(a, b, /, *args, **kwargs)` for `Concatenate[A, B, P]`, and nothing for `Callable[..., R]`; FEAT-2 adds `__call__`'s signature without its receiver for a callback Protocol, so `_check_callable_signature` stays a thin caller of `call_conforms`.

Rejected: **struct-like only**, which refuses a function that a type checker accepts, so the more precise annotation would be the harder one to configure; **out of scope**, leaving the crash.
Precedent: jsonargparse's `function_implements_protocol` takes a function only when `get_protocol_members(origin) == ["__call__"]`; PEP 544 presents callback Protocols as `Callable`'s richer spelling.

### A tag under a parameterized Protocol binds through the bases, else reads the defaults

```python
class Source[T](Protocol):
    def get(self) -> T: ...


@dataclass
class NominalBox[T](Source[T]):
    item: T

    def get(self) -> T: ...


@dataclass
class Box[T]:  # structural
    item: T

    def get(self) -> T: ...
```

Under `s: Source[str]`, `{class: NominalBox, item: 3}` binds `NominalBox[str]` through its bases, as `_tagged_struct` already unifies a nominal subclass, so `3` is refused ([a tag binds the class it names through its bases](../../architecture/types/introspection.md#a-tag-binds-the-class-it-names-through-its-bases)).
`{class: Box, item: 3}` has no base reaching `Source`, so it reads its parameters' defaults, `Box[Any]`, as a tag under `Any` does, and builds `Box(item=3)`.
A non-generic `IntSource` (`get -> int`) is accepted under `Source[str]` likewise: annotations are the type checker's.

Rejected: **unifying member annotations** (`Box.get -> T` against `-> str`), the only place annotations would matter, through methods and properties alike; **refusing a generic structural implementer**, which refuses valid code.

### A `type[P]` field takes a concrete class whose methods conform

`t: type[Greeter]` takes a class by the method half of the rule; there is no instance, so data members go unchecked.
A Protocol class itself is refused, `Greeter` and a sub-Protocol `Loud(Greeter, Protocol)` alike, as PEP 544 rules and mypy enforces (`Can only assign concrete classes to a variable of type "type[Greeter]"`); `ty` does not enforce it yet, and such a class can never be built anyway.
A bare class path under `Callable[..., P]` is checked the same way, methods only, since no instance exists before the factory is called: the same data-member false acceptance, recorded for both.

| `t: <X>` under `type[Named]` | Greeter / Loud | InitAttr | Computed | NoAttr |
|---|---|---|---|---|
| chosen | refused | ✓ | ✓ | ✓ (a false acceptance the type checker catches) |

Rejected: **checking data members by declaration**, which refuses `Computed`.

### A conforming class that is no struct is built as under `Any`

Structural conformance reaches classes inheritance never would: `builtins.str` conforms to a Protocol declaring `upper`, and so can an `Enum` or a registered leaf.
Two recorded decisions already say what a tag naming one builds: the class it names, through `construct_named_class` ([class names the type it builds](../../architecture/design-decisions/class-names-the-type-it-builds.md#class-names-the-type-it-builds)), and a leaf a tag names explicitly is opted back in ([an explicit tag opts a leaf back in](../../architecture/design-decisions/an-explicit-tag-opts-a-leaf-back-in.md)).
So the Protocol field builds it exactly as an `Any` node does: `{class: uuid.UUID, hex: ...}` builds the UUID, and `{class: builtins.str}` is refused as under `Any`, `Cannot coerce dict {} to str`, where today, under a `@runtime_checkable` Protocol, it escapes as `ValueError: no signature found for builtin type <class 'str'>` (run).
jsonargparse likewise accepts any conforming class and leaves its instantiation to fail.

Its dump is written as an `Any` node writes it, with the warning an `Any` node gives when its form will not read back.
`_serialize_struct`'s `_tagged_struct` branch only takes a struct (`_is_struct(actual_tp)`), so without this a conforming `str` would fall through to the Protocol's own fields, none, and write `g: {}` with no warning: a dump that reads back as a refusal.
Under `Any` today a `UUID`, a `Path`, an `Enum` member and a `str` are each written untyped, and the first three warn `will not read back as the UUID it holds: an Any node does not read the spec it would be written as back as an equal value` (run); under a Protocol field none reads back, since a plain value needs the tag (until FEAT-59), so each is a foreign value there, warned as `_serialize_foreign` warns.

### A Protocol takes no plain value, for now

`ratio: SupportsFloat` takes `{class: ...}` only, so `--ratio 3.5` is refused with a message naming the tag; jsonargparse 4.53 answers `Expected a dot import path string: 3` the same way.
Reading a Protocol that a scalar satisfies as the union of those scalars is [FEAT-59](../features/FEAT-59-a-protocol-scalars-satisfy-reads-as-their-union.md), designed in [its own plan](a-protocol-reads-the-scalars-that-satisfy-it.md).

## Where it lives

The conformance rule is one new leaf module, `src/confarg/_conformance.py`, importing the standard library only, so `_types`, `_callable`, `_serialize` and `typedload` can all import it without a cycle.
It answers four questions, and nothing else in the package calls `isinstance` or `issubclass` with a Protocol, `_callable._issubclass_safe` included, which today swallows the `TypeError` and answers `False`:

| Question | Function | Asked by |
|---|---|---|
| is this class a Protocol? | `is_protocol(cls)` — `typing.is_protocol` from 3.13, `cls._is_protocol` on 3.12 | everything below |
| which members must an implementer have, of which kind, and is it a callback Protocol? | `protocol_members(proto)` — the effective member map, name → method or data, built once per Protocol from `typing.get_protocol_members` (3.13+) or `proto.__protocol_attrs__` (3.12): a member is a method when the Protocol defines it as a function, `staticmethod` or `classmethod`; each member records whether its own definition is trivial or `@abstractmethod`, from the one `ast` read of the Protocol's source; the four ordering methods are marked; and the map says whether `__call__` is its only member | the two checks below; `_types._is_plain_class` and `_types._is_callable`, which both read the callback answer instead of deriving it |
| can this implementation be called as that signature is? | `call_conforms(impl, expected)`, landed with BUG-291 | the class check; `_callable._check_callable_signature`; a callback Protocol's resolved value (FEAT-2) |
| does this class, or this instance, satisfy the Protocol? | `class_conforms(cls, proto)` — the methods, holding only the per-pair logic (where each member is found, the call-shape walk, the reason as data); `instance_conforms(value, proto)` — methods on its class, then data members with `hasattr` | `_types._tagged_struct`; `_types._type_ref_admits`, which `_coerce_type_ref` and the dump ask; `_callable._unproducible_return` (a Callable whose declared return is a Protocol); `typedload._holding._variant_holds`, which the dump and construction both ask of a built instance (BUG-293); construction after a named class is built under a Protocol |

Whether a class may be built at all is not `_conformance`'s question: `_construct_named` refuses a Protocol class through `is_protocol`, as decided above (BUG-296, landed).

`protocol_members` is only ever asked of a class `is_protocol` answered for, and says so in its `Dev Notes:`: asked of a nominal implementer, `typing.get_protocol_members` raises on 3.13 to 3.15, while 3.12's `__protocol_attrs__` silently answers with the set the implementer inherits, the worse failure since nothing catches it.
Its guard raises a `TypeError` of its own wording on every version, never `typing`'s: asking it of a class that is no Protocol is a programming mistake, which an `except ConfargError` meant for configuration input must not catch, the reasoning `_union_args` already gives for refusing a recursive alias.
A test on each side of 3.13 pins that the guard holds.

`instance_conforms(value, proto)` is `class_conforms(type(value), proto)` followed by the data-member check on the value, so the method half is spelled once.
Both caches key on the resolved classes (`_class_of(_resolve_type(...))`), so `Source[str]` and `Source` share one entry, as the member set does not depend on the arguments.

Both answers are fixed once their classes exist, so both are cached, keyed weakly as the introspection caches are ([introspection is cached per class](../../architecture/types/introspection.md#introspection-is-cached-per-class)): `protocol_members` per Protocol, since the kind dispatch asks it for every class it classifies, and `class_conforms` per pair, weak on both sides — a `WeakKeyDictionary` on the class holding a `WeakKeyDictionary` on the Protocol — so a Protocol made at runtime lives no longer than it would without the cache.
The instance check is not cached.

`_conformance` never raises for configuration input; only the misuse guard above does.
Each check returns its answer and, on a refusal, the reason as data — the missing member, or the parameter that does not fit — and the caller raises it through `TypeCoercionError`, so `exceptions` stays out of the leaf's imports.
Two factories say "is not a subclass of" today and both gain the Protocol wording, "does not implement", with the reason: `not_a_subclass`, raised by `_coerce_type_ref`, and `tag_not_a_subclass`, raised at the tag by `_construct_by_class_path`; the Protocol is named by its dotted path, its arguments as `_spell_type` spells a parameterized one.
A call-shape refusal names positions and kinds, since a `Callable[[int], int]` has no parameter names: "expects one positional parameter, but `kw_only` takes `x` by keyword only"; the wording tests pin it.
The members are walked sorted, so the one a refusal names does not vary with hash randomization from run to run, as `_coerce_kwargs` sorts the names it reports.

`_tagged_struct` stays the one decision-maker for "which struct does a tag naming this class build here" ([invariants](../../architecture/invariants.md#delegate-to-the-canonical-function)): for a Protocol target it asks `class_conforms`, and a nominal implementer (the Protocol in its `__mro__`) still binds its type parameters through `_ancestor_args`.
`_types._type_ref_admits`, which `_coerce_type_ref` reads a `type[X]` value by and the dump writes one by (BUG-294, landed), stops calling `issubclass` on a Protocol class of the bound and asks the same question through the same module.

A Protocol becomes a struct with no members of its own that demands the tag.
`_types._demands_tag(tp)`, named for the question rather than the mechanism, answers whether a tag is required: [BUG-295](../bugs/BUG-295-a-union-offers-an-untagged-value-to-a-variant-that-demands-its-tag.md) introduces it for a struct with subclasses, and FEAT-57 extends it to a Protocol; it lives in `_types`, which already owns the subclass knowledge and imports `_conformance` for the rest.
Its askers are the three sites that ask `_direct_struct_subclasses(tp)` today — construction (`_construct_struct_dispatch`), flag registration (`cli._build._collect_struct_specs`, which registers `--<field>.class` with a note saying "a class implementing 'Greeter'"), the default layer (`_default_layer`, which lays nothing below an untagged one) — and union disambiguation (`_disambiguate_struct`), which BUG-295 makes leave such a variant out of the untagged match.
`_union_tag_shadowed` is a fifth reader and keeps its own rule unchanged: where a member owns the tag's spelling the tag is not demanded, as decided above.

The dump needs no asker: a value under a Protocol is never of the Protocol's class, so `_serialize_struct` writes the implementer's tag through its `_tagged_struct` branch, in a union as elsewhere (`Base | int` holding an `Impl` dumps `{'name': 'd', 'class': 'abcmod.Impl'}` today, run).
`_serialize._needs_tag` answers a different question, whether a union's variants are told apart, and stays as it is.

A `type[P]` field's dump checks the class it holds against `P`, through the predicate `_coerce_type_ref` reads it back with, `_types._type_ref_admits`, so a non-conforming class is written as a foreign value, with its warning; BUG-294 made that so for every `type[X]`, and the Protocol branch needs nothing more on the dump's side.
`_types._struct_fields` of a Protocol is empty, through the `_constructor_parameters` reading above.

A callback Protocol is not a struct: `_is_plain_class` answers `False` for a Protocol whose only member is `__call__`, so `_is_struct_variant` does not claim it in `_KIND_ORDER` (`typedload._coerce`), where `STRUCT` is asked before `CALLABLE`, and the `_is_callable` row answers it with `CALLABLE`.
That is the non-disjoint case the table's order exists for ([shape dispatch](../../architecture/types/introspection.md#shape-dispatch)), and every walk — construction, dump, the CLI type walk, opener and `args` flag registration — takes the Callable branch for it.

## Phases

1. BUG-291, landed: `_conformance.call_conforms`, `_types._expected_call_signature`, and `_check_callable_signature` rewritten on them.
2. **[BUG-293](../bugs/BUG-293-a-call-result-is-taken-unchecked-when-its-outer-class-matches.md)**, landed before FEAT-57's third step: its design pass made `_callable._accepts` and `_serialize._holds` one predicate, `_holds`, moved to `typedload/_holding.py` and asked by construction of every built instance ([its plan](a-calls-value-is-read-by-construction.md), after BUG-297 and FEAT-60), so FEAT-57 writes its Protocol branch once, in that predicate.
   FEAT-57 is `blocked_by` it for that reason.
   **[BUG-295](../bugs/BUG-295-a-union-offers-an-untagged-value-to-a-variant-that-demands-its-tag.md)** introduces `_demands_tag`, which FEAT-57's second step extends, and BUG-294 (landed) the `type[X]` predicate FEAT-57 extends; both land first too.
   BUG-296, the refusal of a Protocol class in `_construct_named`, has landed, and `_conformance.is_protocol` with it.
3. **[FEAT-57](../features/FEAT-57-protocol-typed-fields.md)**, in this order, each step green before the next; each step's revision description names the raw-`TypeError` sites still open at its boundary:
   1. `protocol_members` (the effective map, trivial bodies and the ordering four included) and `class_conforms`; `_tagged_struct`, `_type_ref_admits` and `_unproducible_return` on them; `_constructor_parameters` reading `typing`'s synthetic constructor as `object.__init__`'s, so no step ever shows the synthetic `args` and `kwargs` as members in `--help`, the type walk or a reference.
      This ends the raw `TypeError` everywhere `_tagged_struct` was reached: at the tag, in `type[P]`, for a `Callable[..., P]` factory, and through `_struct_subclasses` in the type walk (`_struct_member_type`, `_struct_member_names`, `_union_tag_shadowed`, hence `_advance_field_type`), in flag registration (`_collect_struct_specs`) and in the default layer; `_variant_holds` still raises it, asked by `dump()` and by construction of a built instance, a `call:` value's or a caller's.
      The same fix switches the subclass scan on below a Protocol, filtered by conformance, so its tests land in this step.
   2. `_demands_tag` extended to a Protocol, for its four askers.
      Still raising: the same two sites.
   3. `instance_conforms`: the data-member check after construction, and the holding predicate BUG-293 left on it; a conforming non-struct value dumped as an `Any` node writes it, with its warning.
      No raw `TypeError` site is left.
   4. Generic Protocols.
4. **[FEAT-2](../features/FEAT-2-a-callback-protocol-reads-as-a-callable.md)**: `_is_plain_class` refusing a callback Protocol and `_types._is_callable` answering it, the two together; `_expected_call_signature` answering a callback Protocol's `__call__`; `_unproducible_return` reading `__call__`'s return annotation.

## Verification

Each row of the tables above becomes a test against the `loader` fixture, so a file, the environment and argv reach it through all five front-ends ([testing](../../architecture/testing.md)):

- `class:` naming Nominal, Structural, LaxSig builds; BadSig, NoAttr, `greet = 3` and an unrelated class are refused with a `ConfargError` naming the member or parameter; argv and the environment spell the same (`--g.class`, `APP_G__CLASS`).
- The same refusal, word for word, across two builds of it (the members are walked sorted).
- `{class: pkg.Greeter}` and `{class: pkg.Loud}` under `g: Greeter`, under `Any` and under a Callable are refused as Protocol classes, never reaching `Protocols cannot be instantiated`.
- An `@overload`ed Protocol method: a structural implementer defining it builds, a nominal one leaving it unimplemented is refused; an `@abstractmethod` member with a real body, inherited, is refused.
- A `property` provided where the Protocol declares a method is refused; an `async def` where it declares a plain method is accepted, as recorded.
- The dump of a Protocol field holding a conforming non-struct value, in a plain field and in a union, warns that it will not read back.
- A custom `union_tag` a nominal implementer's field owns, inside a union beside an all-defaults struct: `{}` builds the struct, as BUG-295 rules for a variant whose tag is shadowed.
- A `typing_extensions.Protocol` field behaves as a `typing.Protocol` one, on 3.12 and 3.13+ (`typing_extensions.Protocol is typing.Protocol` is `False` on 3.12, run), skipped where `typing_extensions` is not installed.
- `Callable[..., Named]` given the bare path of a class whose methods conform: accepted as a factory, as recorded.
- A plain-class nominal implementer with no `__init__` of its own: `{class: pkg.Impl}` builds and `{class: pkg.Impl, name: x}` is refused as an unknown field, before and after the class's first instantiation.
- A custom `union_tag` spelled like a nominal implementer's field, tagged and untagged: the field's value, the structural selection and its warning, as under an ABC.
- An untagged value, an empty dict and a missing value under a Protocol, with and without a nominal implementer imported; the message names the flag and offers the implementers as examples.
  The examples come from `__subclasses__()` at refusal time, so an import between two refusals changes them: a test pins that a conforming example appears, never the list.
- `--help` of a Protocol nobody inherits: the tag flag's note with no example to offer, the message's commonest real shape.
- `Partial` refused and `Inherits` built; a nominal subclass that does not conform is left out of `--help`, of the type walk and of the tag's shadowing.
- `{class: uuid.UUID, hex: ...}` under a Protocol `UUID` satisfies builds it; `{class: builtins.str}` gets `Any`'s refusal.
- `{}` under `Greeter | AllDefaults` builds `AllDefaults`, and under `Greeter | Needs` gives the union refusal naming `Greeter`'s demand for a tag.
- The dump of a Protocol variant in a union under `tag_policy="auto"` writes the implementer's tag and reads back.
- A `type[P]` field holding a non-conforming class dumps with the foreign-value warning.
- A Protocol field set across layers: `--g.class pkg.Impl` from one source, `--g.name x` from another.
- A Protocol with no members, and a Protocol defining `__init__`.
- `f: Callable[..., Greeter]` given the bare path of a conforming class: a factory, where today it is refused.
- `protocol_members` asked of a nominal implementer is refused by its guard, on 3.12 and on 3.13+ alike.
- A class with no `__call__` of its own is refused under a Protocol declaring `__call__` beside another member, though `getattr_static` finds `type.__call__` on it.
- `{class: pkg.Structural}` under `Greeter | Named` builds `Structural`, once BUG-300 has landed.
- `--help` of a Protocol field lists `--g.class` and a nominal implementer's flags; naming a structural implementer earlier on the line lists its flags ([a named tag is imported before registration](../../architecture/design-decisions/a-named-tag-is-imported-before-registration.md#a-named-tag-is-imported-before-registration)).
- `dump()` of a Protocol field writes the tag and reads back; a non-conforming value is written as `_serialize_foreign` writes it, with its warning.
- A `call:` spec on a Protocol field: a conforming result is taken, any other built as the annotation, hence refused.
- A Protocol in a union beside a struct, in a `list[P]`, a `dict[str, P]`, an optional, and as the root target.
- `type[P]`, generic Protocols, `SupportsLT` and `SupportsEq` against `Bare`, a `@runtime_checkable` Protocol giving the same answers as a plain one.
- The callback Protocol table, through every Callable spec and the dump.

Run the touched tests on 3.12 to 3.15: the introspection API differs between 3.12 (`__protocol_attrs__`, `_is_protocol`) and 3.13+ (`typing.get_protocol_members`, `typing.is_protocol`).

## What moves to the architecture notes when it lands

- A design decision, "a class conforms to a Protocol by its members and call shapes", carrying the conformance, data-member, `object`-member and `type[P]` sections above with their rejected alternatives and precedents.
- A design decision, "a callback Protocol reads as a Callable", from FEAT-2.
- [class names a subclass](../../architecture/design-decisions/class-names-a-subclass-call-computes.md#class-names-a-subclass-call-computes): "a subclass of it" becomes "a subclass of it, or a class implementing it when it is a Protocol".
- [introspection](../../architecture/types/introspection.md): a Protocol in the shape list; the binding rule for a structural implementer under a [tag binds through its bases](../../architecture/types/introspection.md#a-tag-binds-the-class-it-names-through-its-bases).
- [callables](../../architecture/callables.md#a-callable-is-checked-by-its-call-shape): a Protocol method's expected signature, its receiver, and the gradual pair it may declare.
- [invariants](../../architecture/invariants.md): a decision-maker row, "does this class or value satisfy a Protocol?" → `_conformance`.
- [limitations](../../architecture/limitations.md): annotations are not compared; a method is accepted where a data member is declared; a `type[P]` field does not check data members; a method member stored on the instance is refused, where mypy accepts it; a custom `union_tag` a nominal implementer's field owns leaves structural implementers unreachable; a structural implementer is in `--help` only once named; a Protocol takes no plain value (until FEAT-59).
- [limitations](../../architecture/limitations.md), continued: a stub inherited from a Protocol whose source cannot be read counts as an implementation; a bare class path under `Callable[..., P]` does not check data members either; a coroutine function where a plain method is declared, or the reverse, is accepted where ty and mypy refuse it; a conforming non-struct value dumps with a warning, since nothing reads it back under a Protocol until FEAT-59.
- [types/construction](../../architecture/types/construction.md#union-construction): a variant that demands its tag takes no part in structural matching (BUG-295).
- [introspection](../../architecture/types/introspection.md#introspection-is-cached-per-class): `typing`'s synthetic constructor, which a class replaces on its first instantiation, read as `object.__init__`'s so the per-class cache cannot go stale.
- User documentation: the README's "Inheritance" section gains Protocol fields, and `docs/glossary.md` the word.

## Related, not part of this plan

- [BUG-300](../bugs/BUG-300-a-tag-matching-variants-of-two-classes-is-refused-as-ambiguous.md): a tag matching variants of two classes is refused as ambiguous, which a union of two Protocols meets whenever a class implements both.
- [BUG-269](../bugs/BUG-269-a-constructors-own-exception-escapes-construction-raw.md): an implementer that is still abstract escapes as `Can't instantiate abstract class`, as an ABC does today.
- [FEAT-39](../features/FEAT-39-a-struct-instance-default-is-no-base.md): a Protocol field's default is always an instance, so `--g.name z` over it is refused for want of a tag, as under an ABC, until instance defaults are laid.
- [FEAT-58](../features/FEAT-58-a-kwargs-parameter-takes-extra-keys-typed-by-its-annotation.md): a target's `**kwargs`, the other half of what FEAT-2 used to hold.
- [BUG-292](../bugs/BUG-292-a-help-group-is-headed-by-a-docstring-its-class-inherits.md): without it, a Protocol field's `--help` group would be headed by `typing.Protocol`'s docstring.
