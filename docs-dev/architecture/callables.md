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
| `{bind: T, args: {<args>}}` | arguments of the target `T` | `functools.partial(T, **args)`; with no argument, `T` itself |
| `{call: T, args: {<args>}}` | arguments of the target `T` | `T(**args)`, the value it returns |
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
Callable field whatever opener it holds. On a field of any other type, only `call:` is
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

`{bind: T, args: {<args>}}` is `functools.partial(T, **args)`. With no argument it is the bare
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

The key stops being a spec where the annotation could hold it as data: a `dict` type, `Any`, a
Callable (which has its own rules), and a struct with a member named `call`. Those keep the
value as written. The check is per construction in
`typedload._construct._is_typed_call`, so a `call` key means a call on one field and data on
another ([design decision](design-decisions/call-yields-to-the-data-a-type-holds.md)).

On the CLI the key is spelled where it is a spec: `--n.call pkg.f` opens the call, and its
arguments are `--n.args.<p>`, whatever opened it ([CLI](#cli)).

A call is a finished value, so in the merge it replaces what a lower layer set at its node, as a
union tag does; a layer holding only `args` refines the call below it
([a call replaces what lies below](design-decisions/a-call-replaces-what-lies-below.md#a-call-replaces-what-lies-below)).

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
(`--f.bind.class pkg.H --f.bind.x 1`), and how the arguments are (`--f.args.p 2`).

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
| an instance method, whoever built its owner | the path through its owner's class beside the fields the owner holds, as a `classfn:` spec; the bare path when the owner's constructor takes no argument ([a bound method dumps its owner's state](#a-bound-method-dumps-its-owners-state)) |
| `bind:` | `{bind: <target>, args: {<keywords>}}`, whatever the keywords spell; a bare path when nothing is bound. The target is serialized by these same rules |
| `class:` | the spec stamped on the instance as `__confarg_spec__` |
| `classfn:` | the instance method it yields, by the row above |
| `call:` | the callable it returned, by the rows above |

The stamp is best effort, since some objects refuse attributes. A partial over a `class:`
instance dumps the stamp as its nested target. The stamp holds the arguments the instance was
built with ([limitations](limitations.md#callables-and-serialization)). A stamp is merged data,
so it leaves through `_serialize_untyped`, which unwraps the CLI's tokens as it does in a raw
dict.

A callable that no configuration spells, such as a closure, a lambda or an instance no spec
built, cannot be dumped. The merged dict keeps the `call:` that produced it, and
`dump_file(merge(...))` writes it as written.

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
written beside the path ([a bound method dumps its owner's state](#a-bound-method-dumps-its-owners-state)).

Precedent: `pickle` writes a function by reference the same way, which catches every
unimportable or shadowed name, not only the two markers
([dotted imports](types/dotted-imports.md#a-dotted-path-is-written-only-when-it-imports-back)).

### A bound method dumps its owner's state

The path of an instance method reads back bound to an owner built with no arguments, which is the owner again only when the owner holds nothing such a build lacks. So a method dumps as the `classfn:` spec that builds its owner with the state it holds: the owner is read as a struct field is, each constructor parameter off the same-named attribute (`_serialize._serialize_struct`, handed to `_serialize_callable` by the serializer, which knows the path, the union tag and the tag policy). Whoever built the owner — auto-binding, a `classfn:` spec, a `call:` factory or the program — and whatever changed in it after `build()`, the dump holds what the owner holds ([the object dump writes state](design-decisions/the-object-dump-writes-state.md#the-object-dump-writes-state)). `_callable._bound_method_spec` is the one place that decides it.

An owner whose constructor takes no argument dumps as the bare path, since a no-argument build is the only one it has. That is asked of `inspect.signature(owner)`, not of the struct introspection, which reads an inherited `object.__init__` as `*args` and `**kwargs` fields. Two owners are refused, since no spec builds them: one whose class is no struct, such as an `Enum` member, and one with a field named `classfn`, which a spec cannot hold beside its opener ([an opener's word is never an argument](#an-openers-word-is-never-an-argument)). An owner that keeps a constructor argument under another name is refused as a plain class field is.

The `classfn:` owner used to be stamped with its spec, as a `class:` instance still is. The stamp held the arguments the owner was built with, so a change made after `build()` was lost; a frozen owner refused it; and an owner the program or a factory built had none, so its method dumped as the bare path and read back bound to a fresh owner, its state gone with no error (BUG-229).

Rejected:

- **Write the bare path only for an owner auto-binding built**, marked as it is built, and refuse any other. A method of an owner the program built with no arguments would be refused though its path reads back, and a change made after `build()` would still be lost.
- **Write the bare path when the owner's fields equal a no-argument build's.** `dump()` would build an object to compare with, and the path check builds nothing.

Precedent: `pickle` reduces a bound method to `getattr(owner, name)` and pickles the owner by the state it holds, never by replaying its constructor; pydantic's `model_dump` and cattrs' `unstructure` read attributes the same way.

## CLI

A Callable field's openers are registered statically; the target's parameters are
discovered from the named target at `populate_*` time
([CLI adapters](cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags)).
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
([CLI parsing](cli-parsing/token-consumption.md#token-consumption)). An opener flag is not a
refinement but a rival spelling of the target, so it replaces the shorthand rather than joining
it, matching how an opener beats the `{…}` blob it sits next to.
