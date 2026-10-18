# Classfn names an instance method

`{classfn: C.m, <init>}` builds `C(**init)` and yields its bound method `m`. The other keys
of a `classfn` spec are the owner's constructor arguments. The method's own arguments sit under
the `args` of a `bind:` or a `call:` whose target is the `classfn` spec:
`{bind: {classfn: C.m, k: 1}, args: {k: 2}}` is `partial(C(k=1).m, k=2)`, and
`{call: {classfn: C.m, k: 1}, args: {k: 2}}` is `C(k=1).m(k=2)`. So the two namespaces never
meet, even when the owner and the method share a parameter name ([a computation's arguments nest under args](a-computations-arguments-nest-under-args.md#a-computations-arguments-nest-under-args)).

The surrounding rules, settled with it:

- **Instance methods only.** A function, a class, a static method or a class method needs no
  owner to be built, so `classfn:` refuses it, and the message points to `bind:`.
- **The owner is the class the path names**, read by `_callable._instance_method_owner` off
  the path's parent, never off the method's `__qualname__`. `Sub.m`, where `m` is defined on
  `Base`, is owned by `Sub`. The method must be a Python function that the class holds,
  through `inspect.getattr_static`. A static method, a class method and `__init__` are not
  instance methods. Neither is a method that a C type defines (`str.upper`): it stays the
  unbound descriptor it always was.
- **A bare path to an instance method still builds its owner with no arguments.** The same
  applies under `bind:` and `call:`, since they resolve a path target through the same
  `_import_target`. When the owner needs arguments, the error gives the `classfn:` spec to
  paste, with the constructor's parameters listed in it. Raising on every bare instance method
  was the other answer FEAT-27 left open, and the default was kept: an owner that takes no
  arguments loses nothing by being built implicitly.
- **`call:` takes any callable spec as its target, as `bind:` does.** Both resolve their target
  through `_callable._resolve_target`. A `call:` target restricted to `classfn:` was rejected
  for the reason given in [bind yields a partial](bind-yields-a-partial-of-its-target.md): any
  callable spec as a target covers that case, and others too, such as calling a `class:`
  instance.
- **A `classfn:` result dumps as its spec.** A bound method cannot carry an attribute, so the
  owner is stamped with the spec, and `_serialize_callable` reads it back when the stamp holds
  a `classfn` opener.

Rejected:

- **The removed `fn: C.m` with constructor siblings.** It made the meaning of a sibling depend
  on whether the target was a method or a function. `classfn` gives the owner its own opener
  instead.
- **Owner detection by `__qualname__`.** It built the base class for an inherited method, and
  it built an owner for a static or class method, which then failed when that owner needed
  arguments.

Precedent: neither Hydra's `instantiate` nor jsonargparse has a method form, which is why
`classfn` is new. Hydra's `_target_` names a callable to call, and its arguments sit beside it,
which is the shape `classfn` follows for the owner.

Cost: a constructor parameter named `classfn` cannot be filled beside the opener, since two
object openers are refused; it is reached under the `args` of a `call` or a `bind` of the class.
