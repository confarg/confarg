# Callables, bindings and factories

A `Callable[...]` field, and any field a `call:` fills, is configured with data that names
something importable. Implementation: `_callable.py`, called from `typedload.construct`.

## Spec grammar

A spec is a dotted path, or a dict holding exactly one **opener** and the opener's arguments.
There are four openers, and one rule for all of them: **every key beside the opener is an
argument of what the opener builds**.

| Spec | Its siblings are | Yields |
|---|---|---|
| `{bind: T, <args>}` | arguments of the target `T` | `functools.partial(T, **args)`; with no sibling, `T` itself |
| `{call: T, <args>}` | arguments of the target `T` | `T(**args)`, the value it returns |
| `{class: pkg.C, <args>}` | arguments of `C`'s constructor | the instance `C(**args)` |
| `{classfn: pkg.C.m, <args>}` | arguments of the owner's constructor | the bound method `C(**args).m` |
| `"T"` | — | `{bind: T}` |

`bind:` and `call:` name a **target**: a dotted path, or a callable spec of its own, resolved
one key below through `_resolve_target`. `class:` and `classfn:` name a class or a method by
dotted path only. So the openers compose rather than multiply: what `bind:` and `call:` do to a
target does not depend on how the target was built.

| Spec | Result |
|---|---|
| `"pkg.func"` | the function (an instance method is bound to its owner built with no arguments, [auto-binding](#auto-binding)) |
| `"pkg.Class"` | the class used as a **factory**: `functools.partial(Class)`; calling it builds an instance |
| `{bind: pkg.func, a: 1}` | `partial(func, a=1)` |
| `{bind: pkg.Class, a: 1}` | a factory with pre-applied constructor arguments |
| `{bind: {class: pkg.H, x: 1}, p: 2}` | `partial(H(x=1), p=2)` |
| `{bind: {classfn: pkg.C.m, k: 1}, k: 2}` | `partial(C(k=1).m, k=2)` |
| `{call: pkg.factory, a: 1}` | `factory(a=1)`; under a Callable, the callable it returns |
| `{call: {classfn: pkg.C.m, k: 1}, k: 2}` | `C(k=1).m(k=2)` |
| `{class: pkg.H, x: 1}` | the instance `H(x=1)`, which under a Callable must define `__call__` |
| `{classfn: pkg.C.m, k: 1}` | the bound method `C(k=1).m` |

A second opener, or none, is refused. A spec is resolved on a Callable field whatever opener it
holds. On a field of any other type, only `call:` is dispatched
([call in a typed field](#call-in-a-typed-field)), and `class:` is the union tag.

Why one rule: the grammar this replaced had two namespaces of arguments, the siblings and a
`bind:` kwargs dict, and which one an argument belonged in depended on the opener. With `bind`
an opener, every argument sits beside the opener that consumes it, and a partial over an
instance is a `bind:` whose target is the `class:` spec rather than a second dimension of
`class:` ([bind yields a partial](design-decisions/bind-yields-a-partial-of-its-target.md)).
The `fn:` opener and the `bind:` kwargs dict were removed outright, with no deprecation period
and no migration error: `fn` is an ordinary key, and a dict under `bind:` is a target spec, so
`bind: {a: 1}` is refused one key below as a spec with no opener.

**Targets are named, never evaluated.** A target is a dotted path or a spec; `call:` does not
evaluate an expression string. A `${...}` in a spec is resolved before construction like any
other, so it can compute the path or an argument, but not run the call
([calls and expressions](expressions/resolution.md#calls-and-expressions-share-one-graph)).

Precedents: Hydra's `instantiate` keeps `_target_` and its arguments in one mapping, and asks for
a partial with `_partial_: true` rather than nesting the arguments under it; jsonargparse checks
a `class_path` against the annotation, as a typed `class:` is. Neither has a method form, which
is why `classfn:` is new ([classfn](design-decisions/classfn-names-an-instance-method.md)).

## The openers

### Bind yields a partial

`{bind: T, <args>}` is `functools.partial(T, **args)`. With no sibling it is the bare `"T"`,
not `partial(T)`, so a string and its dict form are one spec, and the shorthand rule that opens
`"T"` into `{bind: T}` before a sibling refines it never changes the value of a field that the
sibling did not touch. `{bind: T}` and the bare `"T"` resolve through the same
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

`{call: T, <args>}` calls the target with its siblings and takes the return value. Under a
Callable, the value must be callable, and it is the field. The target may be any callable spec,
as under `bind:`: `{call: {classfn: C.m, k: 1}, k: 2}` is `C(k=1).m(k=2)`, and
`{call: {class: H}}` calls an instance.

`call:` may build a class, `{call: pkg.Foo}`, but it reads as a computation, so declaring a
field's type stays the job of `class:`
([class names a subclass; call computes](design-decisions/class-names-a-subclass-call-computes.md)).

### Call in a typed field

A `call:` spec also fills a field whose annotation is not a Callable: an `int`, a dataclass, an
`Optional`, any other type. The function is called with the sibling keys as its arguments, and
its value is the field. A value the annotation already accepts is taken as it is; any other is
built as the annotation, so a wrong type fails the way a wrong literal does. A `bind:` beside
it is a second opener, refused as in a Callable spec. `dump()` writes the value, not the spec
([the object dump writes state](design-decisions/the-object-dump-writes-state.md#the-object-dump-writes-state)).

The key stops being a spec where the annotation could hold it as data: a `dict` type, `Any`, a
Callable (which has its own rules), and a struct with a member named `call` (`_call` in the
escaped form). Those keep the value as written. The check is per construction in
`typedload._construct._is_typed_call`, so a `call` key means a call on one field and data on
another ([design decision](design-decisions/call-yields-to-the-data-a-type-holds.md)).

On the CLI the key is spelled where it is a spec: `--n.call pkg.f` opens the call, and its
arguments are `--n.<p>` once the command line opens it ([CLI](#cli)).

### Class builds an instance

`{class: C, <args>}` builds exactly `C`, through `typedload._construct.construct_named_class`,
never through the subclass dispatch a struct field runs
([class names the type it builds](design-decisions/class-names-the-type-it-builds.md)). Under a
Callable the instance is the callable. On a typed field `class:` is the union tag, which selects
a struct and builds it from its sibling keys
([union tag](design-decisions/union-tag-defaults-to-class.md)); it must name the annotation or a
subclass of it, and any other class is refused with a message pointing to `call:`
([class names a subclass](design-decisions/class-names-a-subclass-call-computes.md)).

`class:` stays a keyword beside `call:`, though `call:` can build a class too: `class:` says "the
type I want", and `call:` says "compute the value". `class:` never stands in for `call:`.

### Classfn builds the owner

`{classfn: C.m, <init>}` builds the owner from the sibling keys and yields its bound method.
The siblings go through the same construction as a `class:` spec's constructor arguments:
`ctx.instantiate`, which builds exactly the named class, whatever subclasses it has
([class names the type it builds](design-decisions/class-names-the-type-it-builds.md)). A
target that is no instance method, and a target that is no dotted path, are both refused. The
method's own arguments belong beside a `bind:` or `call:` whose target is the `classfn` spec, so
the owner's arguments and the method's never meet, even when they share a name.

## Auto-binding

An instance method named by a path, bare or under `bind:` or `call:`, is bound to its owner
built with no arguments. If the owner needs arguments, the error gives the `classfn:` spec to
paste, with the constructor's parameters listed in it. A sibling of `bind:` or `call:` is an
argument of the method, never of its owner. `_instance_method_owner` is the one answer to "is
this path an instance method, and of which class?". The owner is the class the path names,
read off the path rather than the method's `__qualname__`, so an inherited method binds to the
subclass named. A static method, a class method, `__init__` and a C type's method descriptor
are used as they are
([classfn names an instance method](design-decisions/classfn-names-an-instance-method.md)).

## Plain and escaped directives

Directive words sit next to the target's own kwargs, so a parameter named `bind`, `call`,
`class` or `classfn` would collide. The escaped mode swaps every directive for its underscore
form (`_bind`, `_call`, `_class`, `_classfn`) and frees all plain words to be kwargs.

**The opener alone selects the mode for the whole spec**; a directive word in the other form
is ordinary data. Every directive is an opener, so any escaped one selects the escaped mode,
and the only word that can be left as data is a plain one beside an escaped opener. Each spec
selects its own mode, so a nested `bind:` target spec may be escaped while the spec around it
is not. `active_directives(has_key)` is the one canonical mode selector, shared by
construction (`spec.__contains__`), the CLI parser and flag registration (probes over the
flat `{flag}.{name}` namespace), so every channel agrees without duplicating tables. On the
CLI a field's escaped opener likewise beats a plain `--f.bind`, which is then a kwarg named
`bind`.

**A mixed pair is data everywhere, in all five front-ends** (BUG-25). Rejecting
`--f._bind X --f.bind.p V` outright was considered and declined: `bind` beside an escaped
opener is an ordinary key in a config file and in an env var, so a CLI-only rejection would
trade a front-end parity gap for a channel one — and the target whose own parameter is named
`bind` is exactly what the escaped form exists to reach, so no general rule can call the other
spelling a mistake. What is true is that the pair is almost always a typo, so the rejection
construction already produces is made to say so: `_mixed_form_hint` appends *"`bind` is the
plain spelling of the `_bind` opener, but this spec's opener is escaped"* wherever a kwarg
name is turned down. The hint is derived from the name alone, which is sound because a
directive in the **active** form never reaches a kwarg rejection — it was consumed as a
directive — so a directive word that does is necessarily the other form. It fires only where
the name is rejected: a target that really does take a `bind` parameter still gets it, and
`_reject_mixed_form_kwargs` asks the signature before speaking, so the constructor paths that
report through the shared struct construction say the same thing as the rest.

Both spellings of `bind` and `call` are **subtrees** on the CLI, whichever is active:
`_parse_cli._opens_target` accepts either under a `Callable` (and a `call` under a field that
takes a typed call) and leaves the mode question to construction, and the adapters' CLI
channel is the same loop, so the merged dict matches vanilla's key for key. A subtree is how
a nested target spec is spelled (`--f.bind.class pkg.H --f.bind.x 1`).

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

The kwarg check, the arity check and the constructor listing a failed auto-instantiation
prints all count parameters the same way, through `_fillable_params`: every parameter a
signature lists except `*args` and `**kwargs`. None of them drops a parameter named `self`. A
signature already leaves out the receiver of a class or of a bound method, so a `self` still in
one is a parameter the function really declares: `def handler(self, event)` takes two
arguments, and `{bind: handler, self: …}` fills one of them. The constructor listing reads
`inspect.signature(cls)` for that reason, rather than `cls.__init__`, whose signature still
lists the receiver.

## Round-trip

`dump()` writes the state of the built object, never the `call:` that produced a value
([the object dump writes state](design-decisions/the-object-dump-writes-state.md#the-object-dump-writes-state)).
A callable therefore dumps as what it is, opener by opener:

| Built from | Dumps as |
|---|---|
| a function, a class, a static or class method | its dotted path |
| `bind:` | `{bind: <target>, <keywords>}`, in the form `active_directives` reads back with every keyword an argument (`_form_holding`): the escaped form when a keyword is spelled like a plain opener; a bare path when nothing is bound. A keyword spelled like an escaped opener opens a spec in either form, so no spec holds it and the dump is refused (BUG-217). The target is serialized by these same rules |
| `class:` | the spec stamped on the instance as `__confarg_spec__` |
| `classfn:` | the spec stamped on the owner: a bound method refuses attributes, so a method bound to an owner whose stamp holds a `classfn` opener dumps as that stamp |
| `call:` | the callable it returned, by the rows above |

The stamp is best effort, since some objects refuse attributes. A partial over a `class:`
instance dumps the stamp as its nested target. Either stamp holds the arguments the object was
built with ([limitations](limitations.md#callables-and-serialization)). A stamp is merged data,
so it leaves through `_serialize_untyped`, which unwraps the CLI's tokens as it does in a raw
dict.

A callable that no configuration spells, such as a closure, a lambda or an instance no spec
built, cannot be dumped. The merged dict keeps the `call:` that produced it, and
`dump_file(merge(...))` writes it as written.

## CLI

A Callable field's plain openers are registered statically; the target's parameters are
discovered from the named target at `populate_*` time
([CLI adapters](cli-adapters/static-and-dynamic-flags.md#static-and-dynamic-flags)).
They are `--f.<p>` in every mode, since a sibling of any opener is an argument of what it
builds: a `class` target's constructor parameters, the parameters of the function or class a
`bind` or `call` target names, the constructor parameters of a `classfn` target's owner. A
former implicit form, where a bare return type triggered collection of sibling flags, was
removed.

`bind` and `call` keys are subtrees, so a nested target spec merges in every front-end:
`--f.call.classfn C.m --f.call.k 1 --f.k 2` is `{call: {classfn: C.m, k: 1}, k: 2}`. Its
flags are discovered in two places. The nested spec's own siblings sit below the opener, and
are discovered as the nested spec's opener reads them (`--f.call.k`, the owner's constructor).
The outer siblings are the arguments of the callable the nested spec yields
(`cli._build._yielded_callable_path`): an instance's `__call__`, a bound method's own
parameters, a partial's target; a `call` yields whatever its target returns, which names no
signature, so its outer siblings are accepted but not described.

A `call` on a field that is no Callable (`--n.call pkg.f --n.x 4`, [call in a typed
field](#call-in-a-typed-field)) is spelled the same way, nested target specs included
(`--n.call.classfn C.m --n.call.k 1 --n.k 2`), with two differences. The opener is
registered only when typed, on the help-noise ground of the escaped openers: one `call` flag
per field would double `--help`. And a sibling that names no member is accepted only where
the command line opens the call: a flag below the `call` key, a key of a whole `{…}` value, or
a key of a root `--config` file argv names (`_parse_cli._typed_call_openings`). Below an
unopened field, `--port.typo 3` stays the parse error it was
([design decision](design-decisions/a-typed-call-sibling-needs-its-opener-on-the-command-line.md)).
A member keeps winning over a sibling of the same name, so a struct's own field flag keeps its
type. The root opens no typed call: its flags share the namespace with a host framework's own.

The bare-string shorthand takes sibling flags too: `--f pkg.func --f.sep -` is
`--f.bind pkg.func --f.sep -`, because `"pkg.func"` and `{bind: "pkg.func"}` are two
spellings of one spec. `promote_bare_spec` is the single place that writes the equivalence
down, and `_parse_cli._open_callable_shorthand` the single place that decides when to apply
it — before a deeper key descends through the string, in both the CLI and the env loop
([CLI parsing](cli-parsing/token-consumption.md#token-consumption)). The promoted form is always the *plain* `bind`:
the bare string has no escaped spelling, so it is a plain opener. An opener flag, in either
form, is not a refinement but a rival spelling of the target, so it replaces the shorthand
rather than joining it, matching how an opener beats the `{…}` blob it sits next to.
