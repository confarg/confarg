# Callables, bindings and factories

A `Callable[...]` field, and any field a `call:` fills, is configured with data that names
something importable. Implementation: `_callable.py`, called from `typedload.construct`.

## Spec grammar

A spec is a dotted path, or a dict holding exactly one **opener** and the arguments of what it
builds. There are four openers, of two kinds, and the kind says where the arguments sit:

- an **object** opener, `class:` or `classfn:`, builds an instance, and **every other key is one
  of its fields**, as beside a union tag;
- a **computation** opener, `bind:` or `call:`, applies a target, and **its arguments are the
  mapping under `args`**, the only other key it takes.

| Spec | Its arguments are | Yields |
|---|---|---|
| `{bind: T, args: {<args>}}` | arguments of the target `T` | `functools.partial(T, …)` with the arguments applied ([by position where they can](#arguments-go-by-position-where-they-can)); with no argument, `T` itself |
| `{call: T, args: {<args>}}` | arguments of the target `T` | `T(…)` with the arguments applied the same way, the value it returns |
| `{class: pkg.C, <fields>}` | `C`'s constructor's | the instance `C(**fields)` |
| `{classfn: pkg.C.m, <fields>}` | the owner's constructor's | the bound method `C(**fields).m` |
| `"T"` | — | `{bind: T}` |

`bind:` and `call:` name a **target**: a dotted path, or a callable spec of its own, resolved
one key below through `_resolve_target`. `class:` and `classfn:` name a class or a method by
dotted path only. So the openers compose rather than multiply: what `bind:` and `call:` do to a
target does not depend on how the target was built.

| Spec | Result |
|---|---|
| `"pkg.func"` | the function (an instance method is bound to its owner built with no arguments, [auto-binding](#auto-binding)) |
| `"pkg.Class"` | the class used as a **factory**: `functools.partial(Class)`; calling it builds an instance |
| `{bind: pkg.func, args: {a: 1}}` | `partial(func, a=1)` |
| `{bind: pkg.Class, args: {a: 1}}` | a factory with pre-applied constructor arguments |
| `{bind: {class: pkg.H, x: 1}, args: {p: 2}}` | `partial(H(x=1), p=2)` |
| `{bind: {classfn: pkg.C.m, k: 1}, args: {k: 2}}` | `partial(C(k=1).m, k=2)` |
| `{call: pkg.factory, args: {a: 1}}` | `factory(a=1)`; under a Callable, the callable it returns |
| `{call: {classfn: pkg.C.m, k: 1}, args: {k: 2}}` | `C(k=1).m(k=2)` |
| `{class: pkg.H, x: 1}` | the instance `H(x=1)`, which under a Callable must define `__call__` |
| `{classfn: pkg.C.m, k: 1}` | the bound method `C(k=1).m` |

Two openers of one kind, or none, are refused. An object opener reads every other key as a field,
so beside `class` or `classfn` a `bind` or `call` key is a field, not a second opener; beside
`bind` or `call`, a key other than `args` is refused, the message saying the arguments go under
`args`. `_callable._spec_parts` is the one reader of a spec's opener and arguments, and
`spec_opener` its answer for registration, which must not raise. A spec is resolved on a
Callable field whatever opener it holds, and so is one an `Any` node holds
([an `Any` node reads every opener](#an-any-node-reads-every-opener)). On a field of any other type, only `call:` is
dispatched ([call in a typed field](#call-in-a-typed-field)), and `class:` is the union tag.

Why two kinds: an object is its fields, which is how a tagged struct is written everywhere else
in confarg, while a computation's arguments belong to a target that is not the spec, and nesting
them keeps every word of the target's free ([a computation's arguments nest under
args](design-decisions/a-computations-arguments-nest-under-args.md#a-computations-arguments-nest-under-args)).
The grammar this replaced put every argument beside its opener, and needed an escaped set of
openers (`_bind`, `_call`, …) to reach a parameter named like one; before that, a `bind:`
kwargs dict sat beside the other openers, and which namespace an argument belonged in depended
on the opener ([bind yields a partial](design-decisions/bind-yields-a-partial-of-its-target.md)).
Both were removed outright, with no deprecation period and no migration error: `fn` and the
underscored words are ordinary keys, and a dict under `bind:` is a target spec, so
`bind: {a: 1}` is refused one key below as a spec with no opener.

**Targets are named, never evaluated.** A target is a dotted path or a spec; `call:` does not
evaluate an expression string. A `${...}` in a spec is resolved before construction like any
other, so it can compute the path or an argument, but not run the call
([calls and expressions](expressions/resolution.md#calls-and-expressions-share-one-graph)).

Precedents: jsonargparse nests a class's arguments under `init_args` beside its `class_path`,
and checks the `class_path` against the annotation, as a typed `class:` is; GitHub Actions
nests a step's inputs under `with` beside `uses`. Hydra's `instantiate` keeps `_target_` and its
arguments in one mapping, the grammar this replaced. None has a method form, which is why
`classfn:` is new ([classfn](design-decisions/classfn-names-an-instance-method.md)).

## The openers

### Bind yields a partial

`{bind: T, args: {<args>}}` is a `functools.partial` of `T` with its arguments applied, by position where they can ([arguments go by position where they can](#arguments-go-by-position-where-they-can)). With no argument it is the bare
`"T"`, not `partial(T)`, so a string and its dict form are one spec, and the shorthand rule that
opens `"T"` into `{bind: T}` before an argument refines it never changes the value of a field
that the argument did not touch. `{bind: T}` and the bare `"T"` resolve through the same
`_import_target`: the factory check below and [auto-binding](#auto-binding) apply to both.

`bind:` takes a target, never a kwargs dict. A dict under it is a spec of its own, resolved one
key below. `bind:` is not dispatched on a typed field: a partial is a Callable.

### Class as factory versus class as instance

A bare class name, or a class under `bind:`, means "factory". When the `Callable` declares a
concrete return type that the class cannot produce (including `None`), that is almost certainly
a user who wanted an instance, so it raises and points to `class:` instead of silently building
a wrong factory. A bare `Callable`, `Callable[..., TypeVar]` or special form has nothing to
check, so the user is trusted. `get_args(Callable[..., None])` reports the return as the object
`None` (not `NoneType`), which is why `_unproducible_return` reads the raw args. A class named by
`bind:` is the same factory with arguments applied, so the same check holds for it.

### Call computes a value

`{call: T, args: {<args>}}` calls the target with its arguments and takes the return value. Under
a Callable, the value must be callable, and it is the field. The target may be any callable
spec, as under `bind:`: `{call: {classfn: C.m, k: 1}, args: {k: 2}}` is `C(k=1).m(k=2)`, and
`{call: {class: H}}` calls an instance.

`call:` may build a class, `{call: pkg.Foo}`, but it reads as a computation, so declaring a
field's type stays the job of `class:`
([class names a subclass; call computes](design-decisions/class-names-a-subclass-call-computes.md)).

### Call in a typed field

A `call:` spec also fills a field whose annotation is not a Callable: an `int`, a dataclass, an
`Optional`, any other type. The function is called with the arguments under `args`, and its
value is the field. A value the annotation already accepts is taken as it is; any other is
built as the annotation, so a wrong type fails the way a wrong literal does. A `bind:` beside
it is a second opener, and any other key beside it is refused, as in a Callable spec. `dump()` writes the value, not the spec
([the object dump writes state](design-decisions/the-object-dump-writes-state.md#the-object-dump-writes-state)).

The key stops being a spec where the annotation could hold it as data: a `dict` type, a
Callable (which has its own rules), and a struct with a member named `call`. Those keep the
value as written. The check is per construction in
`typedload._construct._is_typed_call`, so a `call` key means a call on one field and data on
another ([design decision](design-decisions/call-yields-to-the-data-a-type-holds.md)). An `Any`
field held the key as data too until FEAT-42; it now reads every opener
([an `Any` node reads every opener](#an-any-node-reads-every-opener)).

On the CLI the key is spelled where it is a spec: `--n.call pkg.f` opens the call, and its
arguments are `--n.args.<p>`, whatever opened it ([CLI](#cli)).

A call is a finished value, so in the merge it replaces what a lower layer set at its node, as a
union tag does; a layer holding only `args` refines the call below it
([a call replaces what lies below](design-decisions/a-call-replaces-what-lies-below.md#a-call-replaces-what-lies-below)). So does every opener on a Callable or an `Any`: `{bind: g}` over a lower `{bind: f, args: {a: 1}}` is `g` alone, while `{bind: {x: 5}}`, naming no target, refines the nested one ([the type decides](design-decisions/the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines)).

### Class builds an instance

`{class: C, <args>}` builds exactly `C`, through `typedload._construct.construct_named_class`,
never through the subclass dispatch a struct field runs
([class names the type it builds](design-decisions/class-names-the-type-it-builds.md)). Under a
Callable the instance is the callable. On a typed field `class:` is the union tag, which selects
a struct and builds it from the other keys
([union tag](design-decisions/union-tag-defaults-to-class.md)); it must name the annotation or a
subclass of it, and any other class is refused with a message pointing to `call:`
([class names a subclass](design-decisions/class-names-a-subclass-call-computes.md)).

`class:` stays a keyword beside `call:`, though `call:` can build a class too: `class:` says "the
type I want", and `call:` says "compute the value". `class:` never stands in for `call:`.

### Classfn builds the owner

`{classfn: C.m, <init>}` builds the owner from the other keys and yields its bound method.
They go through the same construction as a `class:` spec's constructor arguments:
`ctx.instantiate`, which builds exactly the named class, whatever subclasses it has
([class names the type it builds](design-decisions/class-names-the-type-it-builds.md)). A
target that is no instance method, and a target that is no dotted path, are both refused. The
method's own arguments belong under the `args` of a `bind:` or `call:` whose target is the
`classfn` spec, so the owner's arguments and the method's never meet, even when they share a name.

## An `Any` node reads every opener

An `Any` field reads a dict holding an opener (`_callable.holds_an_opener`) as the spec it is, through the same `_spec_parts` a Callable field reads: `{class: pkg.S, a: 1}` builds `S(a=1)`, `{call: pkg.f, args: {x: 4}}` takes `f(x=4)` as it is, `{bind: pkg.f}` yields `f` and `{classfn: pkg.C.m, k: 1}` the bound method. `_callable.resolve_held_spec` is that reader: it checks nothing against a Callable, so `class:` builds any class, callable or not, through `construct_named_class` as a Callable's `class:` does ([class builds an instance](#class-builds-an-instance)). A dict holding no opener is a `dict[Any, Any]` and a list a `list[Any]`, so every value below is an `Any` node in turn and a spec at any depth is read (`typedload._construct._construct_any`); a bare `dict` or `list` annotation reads the same way, being `dict[Any, Any]` and `list[Any]` (BUG-187). A bare dotted string stays a string: the shorthand applies only where the type asks for a callable. A class that does not import, or a path that names no class, is refused, not kept as data. In a union, a tag naming a struct variant selects it as before, and one naming no variant is the `Any` variant's spec (`_construct_union_by_tag`), a Callable variant's when the union has one; a tag that does not import is refused there too. Any other opener is read before a struct or dict variant tries the dict ([a Callable beside another variant](#a-callable-beside-another-variant)).

On the command line a keyed `Any` is a `dict[Any, Any]` as well: `_parse_cli._advance_field_type` answers `Any` for any segment below one, so `--x.class pkg.S --x.a 1`, `--x.call pkg.f --x.args.x 4`, and their environment spellings (`APP_X__CLASS`, `APP_X__A`) reach the same spec a file writes. Since `_takes_typed_call` no longer yields on `Any`, `call` and `args` open a subtree below it as below any typed field, and the adapters describe `--x.args.<p>` from the target's signature. A key below an `Any` that names a class is typed by it, as below a Callable ([a node types its keys by the class it names](design-decisions/a-node-types-its-keys-by-the-class-it-names.md#a-node-types-its-keys-by-the-class-it-names)): `--x.class pkg.J --x.parts a b` takes the run `J`'s `list[str]` takes, `APP_X__PARTS='["a","b"]'` decodes, and a key `J` does not declare is refused. Below an `Any` that names nothing, every flag is an `Any` node, registered when argv types it, as a dict's keys are (`_parse_cli._COLLECTION_KINDS`), one token each.

`dump()` writes what an `Any` holds back as the spec that rebuilds it ([serialization](types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it)). The decision and its rejected alternatives are in [an `Any` node reads every opener](design-decisions/an-any-node-reads-every-opener.md).

## A Callable beside another variant

A union holding a Callable and another variant, `Callable | str`, `Callable | Opts`, builds the Callable from every spelling of a spec, as a lone Callable field does (BUG-234). Each spelling meets the union at one place, and each place has one decision-maker:

| The value | Read by | Example on `Callable[[int], int] \| Opts` |
|---|---|---|
| a string | the scalar walk, in stealing rank: the Callable just below type references and `Literal`, above the numbers and `str` | `pkg.double` is the function; `hello` is refused, as `str` would take it in `Callable \| str` |
| a dict holding `bind` or `classfn` (or `class` when it is not the union tag) | the Callable variant, before any struct or dict variant (`spec_reading_variant`) | `{bind: pkg.add, args: {y: 3}}` is the partial |
| a dict holding the union tag | a struct variant it names, else the Callable variant's spec (`_construct_union_by_tag`) | `{class: pkg.Mul, factor: 3}` is the instance; `{class: pkg.Opts}` the struct |
| a dict holding `call` | the union, which takes the value as a typed call does (`_takes_typed_call`) | `{call: pkg.make_double}` is the function, `{call: pkg.make_opts}` the struct |

The rules are maintainer's choices; [a Callable beside another variant reads its spec](design-decisions/a-callable-beside-another-variant-reads-its-spec.md) has the rejected alternatives. Three of them reach past the Callable:

- **An `Any` variant reads an opener first too**, a Callable variant first when the union has both: `Any | dict[str, str]` reads `{bind: pkg.f}` as the function, where it used to try the dict variant first, so both kinds of spec reader agree.
- **A struct variant owning an opener's key keeps it as data**, as a member owning the union tag's spelling does ([real field wins](cli-parsing/casts-and-reserved-words.md#real-field-wins)): `Callable | Hook`, where `Hook` has a field `bind`, reads `{bind: x}` as a `Hook`. The merge asks the same `spec_reading_variant`, so a later `{bind: y}` refines the `Hook` rather than replacing it ([the type decides](design-decisions/the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines)).
- **A module that fails while importing stops the union**, while a path naming nothing lets the next variant read the string ([dotted imports](types/dotted-imports.md#a-path-names-nothing-or-a-module-fails)).

`dump()` writes the Callable variant's value as a lone Callable's, and checks that it reads back by re-dumping what it reads, since an instance or a partial compares equal to nothing but itself ([casting a stolen leaf](types/stealing-rule.md#casting-a-stolen-leaf)). A string the Callable variant would read, `pkg.double` held as text in `Callable | str`, dumps as `{__cast__: str, __value__: pkg.double}`.

The CLI and the environment merged every spelling already, the walk following the Callable member below the field; construction was what refused them. Below a spec, the walk follows the variant the spec selects (`_naming.named_variant`), so a key is typed by the class its opener names.

## Auto-binding

An instance method named by a path, bare or under `bind:` or `call:`, is bound to its owner
built with no arguments. If the owner needs arguments, the error gives the `classfn:` spec to
paste, with the constructor's parameters listed in it. An argument under the `args` of `bind:`
or `call:` is an argument of the method, never of its owner. `_instance_method_owner` is the one answer to "is
this path an instance method, and of which class?". The owner is the class the path names,
read off the path rather than the method's `__qualname__`, so an inherited method binds to the
subclass named. A static method, a class method, `__init__` and a C type's method descriptor
are used as they are
([classfn names an instance method](design-decisions/classfn-names-an-instance-method.md)).

## An opener's word is never an argument

No parameter name needs escaping. Beside `bind` or `call`, an argument sits under `args`, so a
target's parameter named `bind`, `call`, `class`, `classfn` or `args` is an ordinary key of that
mapping. Beside `class` or `classfn`, every other key is a field, so a constructor's `bind` or
`call` parameter is one too. `class` can name no Python parameter. A constructor parameter named
`classfn` is the one an object opener cannot reach, since two object openers are refused; it is
reached under the `args` of a `call` or a `bind` of the class.

The words `_bind`, `_call`, `_class` and `_classfn` were the escaped set of openers of the grammar
this replaced, which put arguments beside their opener; they are ordinary keys now. Removing
them took with them the mode selection every channel shared (`active_directives`), the hint that
named a mixed pair (BUG-25), and the dump's refusal of a keyword spelled like an escaped opener
(BUG-217): under `args`, every keyword reads back as itself.

`bind`, `call` and `args` are **subtrees** on the CLI (`_callable.opens_a_subtree`):
`_parse_cli._opens_spec_subtree` accepts all three under a `Callable`, and `call` and `args`
under a field that takes a typed call, and the adapters' CLI channel is the same loop, so the
merged dict matches vanilla's key for key. A subtree is how a nested target spec is spelled
(`--f.bind.class pkg.H --f.bind.x 1`), and how the arguments are (`--f.args.p 2`). `bind` and
`call` hold a Callable target, typed by the opener the nested spec holds in turn, and `args` the
target's parameters, typed by the target an opener names and untyped at any depth where none
does ([a node types its keys by the class it names](design-decisions/a-node-types-its-keys-by-the-class-it-names.md#a-node-types-its-keys-by-the-class-it-names)).

## One coercion route

`bind` and `call` arguments go through `_coerce_kwargs`: unknown names raise, and every value
is built with `construct`, the same route as any other configuration element (enums,
dataclasses, unions work in bound arguments). `class` and `classfn` constructor arguments go
through `ctx.instantiate`, the struct construction that builds exactly the named class
([class builds an instance](#class-builds-an-instance)), which refuses unknown names and builds
each value the same way. Signature and annotations are taken from different objects when
needed: `inspect.signature(cls)` gives constructor parameters, but annotations live on
`cls.__init__`; for a callable instance they live on `type(obj).__call__`.

A `call:` reads its annotations from the same object as `bind:` does (`_hints_source`), so
a class it calls is built from its `__init__` annotations, as under `class:` (BUG-155).

Validation is skipped where it cannot work: uninspectable callables (C extensions) and
signature arity checks for `*args` callables or `Callable[..., R]`.

## Arguments go by position where they can

`args` holds a target's arguments by name, but a call does not pass them all by keyword: `_types._PositionalParams.split` decides, the same rule construction applies to a plain class's `__init__` ([types](types/introspection.md#introspection-is-cached-per-class)). `_callable._split_arguments` asks it for `bind:` and `call:` alike.

1. A positional-only parameter left unset before a set one takes its declared default, since no keyword reaches the later one past it: with `def f(a=1, b=2, /)`, `{b: 5}` binds `partial(f, 1, 5)`. With no default to take, the spec is refused at load, naming both parameters.
2. Then the longest run of set positional names from the first goes by position, and every other argument by keyword. With `def g(v, factor)`, `{v: 3}` binds `partial(g, 3)`, `{factor: 2}` binds `partial(g, factor=2)`, and `{v: 3, factor: 2}` binds `partial(g, 3, 2)`.

Why: a positional-only parameter takes no keyword, so it needs a position (BUG-156), as `{call: math.sqrt, args: {x: 16}}` does. Passing the leading run by position too, rather than the positional-only parameters alone, is what makes the dump exact: a partial's positional arguments dump under the names of the parameters they fill ([round-trip](#round-trip)), and those names split back to the same positions. It also lets a `Callable[[int], int]` bound by `{bind: g, args: {v: 3}}` be called `f(5)`, which `partial(g, v=3)` refused with "multiple values for 'v'". `inspect.BoundArguments.args` draws the same line, a positional-or-keyword parameter going by position for as long as every one before it is bound. Hydra's `instantiate` passes every named argument by keyword and reaches a positional parameter only through a separate `_args_` list; confarg keeps one mapping by name.

Cost: a parameter a `bind:` passed by position cannot be passed again by keyword when the partial is called, as one bound by keyword could be. A name under `args` always means the declared parameter, never a key of the target's `**kwargs` ([limitations](limitations.md#callables-and-serialization)).

The kwarg check, the arity check, the constructor listing a failed auto-instantiation
prints and the CLI's `--f.args.<param>` flags for a `bind:` or `call:` target all count parameters
the same way, through `_fillable_params`: every parameter a signature lists except `*args` and
`**kwargs`. Registration reads the signature of the callable construction calls,
`_target_signature`: an instance method bound off its receiver, whatever the receiver is
named, without building the owner (BUG-218). None of them drops a parameter named `self`. A
signature already leaves out the receiver of a class or of a bound method, so a `self` still in
one is a parameter the function really declares: `def handler(self, event)` takes two
arguments, and `{bind: handler, args: {self: …}}` fills one of them. The constructor listing reads
`inspect.signature(cls)` for that reason, rather than `cls.__init__`, whose signature still
lists the receiver.

## Round-trip

`dump()` writes the state of the built object, never the `call:` that produced a value
([the object dump writes state](design-decisions/the-object-dump-writes-state.md#the-object-dump-writes-state)).
A callable therefore dumps as what it is, opener by opener:

| Built from | Dumps as |
|---|---|
| a function, a class, a static or class method | its dotted path, when it reads back as the callable |
| an instance method, whoever built its owner | the path through its owner's class beside the fields the owner holds, as a `classfn:` spec; the bare path when the owner's constructor takes no argument ([an object dumps the state it holds](#an-object-dumps-the-state-it-holds)) |
| `bind:` | `{bind: <target>, args: {<arguments>}}`, whatever the keywords spell, each positional argument named by the parameter it fills (`_named_partial_args`); a bare path when nothing is bound. The target is serialized by these same rules. A positional argument no name holds, one spilling into `*args` or one of a target whose signature cannot be read, cannot be dumped |
| a callable instance, `class:` or whoever built it | its class's path beside the fields it holds, as a `class:` spec ([an object dumps the state it holds](#an-object-dumps-the-state-it-holds)) |
| `classfn:` | the instance method it yields, by the row above |
| `call:` | the callable it returned, by the rows above |

A partial over a callable instance dumps the instance's `class:` spec as its nested target. A
partial's keywords carry no declared type, so the spec leaves through `_serialize_untyped`, which
writes an `Enum` or a `Path` as a raw dict's value; a struct keyword is not written that way
(BUG-194).

A callable that no configuration spells, such as a closure, a lambda, or an instance whose
fields cannot be read, cannot be dumped. The merged dict keeps the spec that produced it, and
`dump_file(merge(...))` writes it as written.

An object an `Any` field holds is written by the same rules, a bare path opened into its `bind:` form, which an `Any` node reads where it reads a bare string as text ([serialization](types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it)).

### A path is written only when it reads back

Having a module and a qualified name does not make a callable importable by them: a closure's
qualified name holds `<locals>`, a lambda's `<lambda>`, and a module may hold another object
under the name, or none. So `_serialize_callable` imports the path it is about to write and
checks that it names the callable (`_reads_back_from`), refusing at `dump()` what used to fail
only on read-back (BUG-193). A class tag and a `type[X]` leaf are checked the same way,
through the `imports_back` they share ([dotted imports](types/dotted-imports.md#a-dotted-path-is-written-only-when-it-imports-back)). The check imports rather than resolves, so nothing is built: an
instance method reads back by [auto-binding](#auto-binding), and stands only when the value is
that method bound to an instance of exactly the class the path names. That is also why a bare
instance method function, `C.m` unbound, is refused: its path reads back bound. A class method is
a new bound method on each access, so it is compared with `==`, which holds for the same function
bound to the same class.

`dotted_name` spells a bound method through the class it is bound to: a method a base defines
has the base in its qualified name, and `"pkg.Sub.m"` loaded through auto-binding would dump as
`pkg.Base.m`, bound to a base on read-back. The check does not see an owner's state, which is
written beside the path ([an object dumps the state it holds](#an-object-dumps-the-state-it-holds)).

Precedent: `pickle` writes a function by reference the same way, which catches every
unimportable or shadowed name, not only the two markers
([dotted imports](types/dotted-imports.md#a-dotted-path-is-written-only-when-it-imports-back)).

### An object dumps the state it holds

The two object openers build an object and dump it back by the state it holds: a `class:` instance is the callable, and a `classfn:` owner is the object its method is bound to. Each is read as a struct field is, each constructor parameter off the same-named attribute (`_serialize._serialize_struct`, handed to `_serialize_callable` by the serializer, which knows the path, the union tag and the tag policy), and written beside its opener: `{class: <its class>, <fields>}`, `{classfn: <the method's path>, <the owner's fields>}`. Whoever built the object — a spec, auto-binding, a `call:` factory or the program — and whatever changed in it after `build()`, the dump holds what the object holds, and reads back as an equal object ([the object dump writes state](design-decisions/the-object-dump-writes-state.md#the-object-dump-writes-state)). `_callable._object_spec` is the one place that decides it for both openers.

An object whose constructor takes no argument holds nothing a no-argument build lacks, so its opener stands alone: `{class: pkg.C}`, and for a method the bare path, which reads back bound to such an owner by [auto-binding](#auto-binding). A `class:` instance never dumps as its bare path, which reads back as the class used as a factory. That the constructor takes no argument is asked of `inspect.signature(cls)`, not of the struct introspection, which reads an inherited `object.__init__` as `*args` and `**kwargs` fields. Three objects are refused, since no spec builds them: one whose class is no struct, such as an `Enum` member; one with a field named `classfn`, which a spec cannot hold beside its opener ([an opener's word is never an argument](#an-openers-word-is-never-an-argument)); and one that keeps a constructor argument under another name, refused as a plain class field is. A `class:` instance's class is also checked to import back from its path, as a class tag is ([dotted imports](types/dotted-imports.md#a-dotted-path-is-written-only-when-it-imports-back)).

Both objects used to be stamped with the spec that built them (`__confarg_spec__`), and the dump wrote the stamp: the `classfn:` owner until BUG-229, the `class:` instance until BUG-192. A stamp looks right at first, since it reads back as exactly what the configuration asked for, but it records the build, not the object, so it misses every change the program makes:

```python
class Hidden:  # keeps its argument under another name
    def __init__(self, factor):
        self._factor = factor

    def __call__(self, x):
        return x * self._factor


cfg = confarg.build(Config, {"f": {"class": "pkg.Hidden", "factor": 3}})
cfg.f._factor = 5  # case 6: stamped {class: pkg.Hidden, factor: 3}, stale, no error
confarg.dump(Config(f=Hidden(3)))  # case 7: no stamp, so refused, though the class is the same
```

A stamp is stale as soon as the program changes the object after `build()` (case 6), and absent from every object the program or a factory built (case 7), so the same class dumped or failed depending on who built it. A frozen dataclass or a `__slots__` class also refused the stamp, and then had nothing to dump from. Reading state has none of those holes: case 6 and case 7 are refused alike, at `dump()`, naming the field it cannot read, and a class that stores its arguments dumps whatever its instance holds.

Rejected:

- **Keep the stamp as a fallback** for an object whose fields cannot be read. It is the class that hides its argument that needs the fallback, and that is exactly the class whose later changes the stamp cannot see (case 6); its instances the program built would still be refused (case 7). Two dump paths for one opener would also disagree for the same class.
- **Read state only for an object a spec built**, marked as it is built, and refuse any other. An object `{class: …}` spells perfectly well would be refused because the program built it, and the mark needs an attribute that a frozen or a slotted object refuses, as the stamp did.
- **Write the bare path when a method's owner equals a no-argument build.** `dump()` would build an object to compare with, and the path check builds nothing.

Precedent: `pickle` reduces an object to its class and the state it holds, and a bound method to `getattr(owner, name)` over the owner pickled that way, never by replaying a constructor; pydantic's `model_dump` and cattrs' `unstructure` read attributes the same way. Hydra and jsonargparse keep the `_target_` / `class_path` configuration and never serialize the instance back, which is the merged dict's job here ([the object dump writes state](design-decisions/the-object-dump-writes-state.md#the-object-dump-writes-state)).

## CLI

A Callable field's openers are registered statically; the target's parameters are
discovered from the named target at `populate_*` time
([CLI adapters](cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags)), whether
argv, a file or the environment names it, and every flag below the spec is typed by the class
its opener names, in vanilla's walk and in registration alike
([a node types its keys by the class it names](design-decisions/a-node-types-its-keys-by-the-class-it-names.md#which-naming-types-a-key)):
`--f.class pkg.Joiner --f.parts a b` takes the run a `list[str]` takes, and
`--f.class pkg.Wrap --f.inner.class pkg.Mul --f.inner.factor 4` opens the nested spec of
`Wrap`'s Callable argument. On argv the opener comes first: a key written before it is untyped.
A `bind` or `call` target's parameters are `--f.args.<p>`, the parameters of the function or
class it names; a `class` target's are `--f.<p>`, its constructor's, and so are a `classfn`
target's owner's. A former implicit form, where a bare return type triggered collection of
argument flags, was removed.

`bind`, `call` and `args` are subtrees, so a nested target spec merges in every front-end:
`--f.call.classfn C.m --f.call.k 1 --f.args.k 2` is `{call: {classfn: C.m, k: 1}, args: {k: 2}}`.
Its flags are discovered in two places. The nested spec's own arguments sit below the opener,
and are discovered as the nested spec's opener reads them (`--f.call.k`, the owner's
constructor). The outer `args` are the arguments of the callable the nested spec yields
(`cli._build._yielded_callable_path`): an instance's `__call__`, a bound method's own
parameters, a partial's target; a `call` yields whatever its target returns, which names no
signature, so its outer arguments are accepted but not described.

A `call` on a field that is no Callable (`--n.call pkg.f --n.args.x 4`, [call in a typed
field](#call-in-a-typed-field)) is spelled the same way, nested target specs included
(`--n.call.classfn C.m --n.call.k 1 --n.args.k 2`), with one difference: the opener is
registered only when typed, on help-noise ground, since one `call` flag per field would double
`--help`. `--n.args.<p>` is accepted below every field a call can fill, whatever opened the
call: a flag, a whole `{…}` value, a `--config` file, a `files=` file or the environment. A
typo below a field that names no `args` (`--port.typo 3`) stays the parse error it was, so
leniency stands only where `args` asks for it
([design decision](design-decisions/a-computations-arguments-nest-under-args.md#a-computations-arguments-nest-under-args)).
A member named `args` or `call` keeps winning, so a struct's own field flag keeps its type. The
root opens no typed call: its flags share the namespace with a host framework's own.

The bare-string shorthand takes argument flags too: `--f pkg.func --f.args.sep -` is
`--f.bind pkg.func --f.args.sep -`, because `"pkg.func"` and `{bind: "pkg.func"}` are two
spellings of one spec. `promote_bare_spec` is the single place that writes the equivalence
down, and `_parse_cli._open_callable_shorthand` the single place that decides when to apply
it — before a deeper key descends through the string, in both the CLI and the env loop
([CLI parsing](cli-parsing/token-consumption.md#token-consumption)). An opener written over a spec already in hand restates it the same way: the node starts afresh, the earlier arguments with it (`_parse_cli._restart_restated_node`, BUG-238). Across layers the merge opens it the same way, asking the same question, so `fn: pkg.func` in a file and `--fn.args.sep -` on argv build the partial too ([the type decides](design-decisions/the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines)). An opener flag is not a
refinement but a rival spelling of the target, so it replaces the shorthand rather than joining
it, matching how an opener beats the `{…}` blob it sits next to.
