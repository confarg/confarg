# Callables, bindings and factories

A `Callable[...]` field is configured with data that names something importable.
Implementation: `_callable.py`, called from `typedload.construct`.

## Spec grammar

| Value | Result |
|---|---|
| `"pkg.func"` | the function (an instance method auto-instantiates its class with no args) |
| `"pkg.Class"` | the class used as a **factory**: `functools.partial(Class)`; calling it builds an instance |
| `{fn: pkg.func, bind: {…}}` | the function, partially applied |
| `{fn: pkg.Class.method, <ctor kwargs>}` | the owning class is built with the sibling kwargs; the bound method is the callable |
| `{fn: pkg.Class, bind: {…}}` | a factory with pre-applied constructor args |
| `{class: pkg.Class, <ctor kwargs>, bind: {…}}` | an **instance** (must define `__call__`) is the callable; `bind` applies to `__call__` |
| `{call: pkg.factory, <kwargs>}` | the factory is called; its return value is the callable |

Exactly one opener (`fn`/`class`/`call`) is allowed.

## Plain and escaped directives

Directive words sit next to the target's own kwargs, so a parameter named `fn`, `call` or
`bind` would collide. The escaped mode swaps every directive for its underscore form
(`_fn`, `_class`, `_call`, `_bind`) and frees all plain words to be kwargs.

**The opener alone selects the mode for the whole spec**; a directive word in the other form
is ordinary data. Do not mix forms. `active_directives(has_key)` is the one canonical mode
selector, shared by construction (`spec.__contains__`), the CLI collector and flag
registration (probes over the flat `{flag}.{name}` namespace), so every channel agrees
without duplicating tables. On the CLI a field's escaped opener likewise beats a plain
`--f.fn`, which is then a kwarg named `fn`.

## Class as factory versus class as instance

A bare class name means "factory". When the `Callable` declares a concrete return type that
the class cannot produce (including `None`), that is almost certainly a user who wanted an
instance, so it raises and points to `class:` instead of silently building a wrong factory. A
bare `Callable`, `Callable[..., TypeVar]` or special form has nothing to check, so the user is
trusted. `get_args(Callable[..., None])` reports the return as the object `None` (not
`NoneType`), which is why `_unproducible_return` reads the raw args.

## One coercion route

`call` kwargs, `class` constructor kwargs and `bind` kwargs all go through `_coerce_kwargs`:
unknown names raise, and every value is built with `construct`, the same route as any other
configuration element (enums, dataclasses, unions work in bound arguments). Signature and
annotations are taken from different objects when needed: `inspect.signature(cls)` gives
constructor parameters, but annotations live on `cls.__init__`; for a callable instance they
live on `type(obj).__call__`. On the CLI, registration finds `__call__` in the class's own MRO,
not via `getattr`, which would return the metaclass `type.__call__` for non-callable
instances.

Validation is skipped where it cannot work: uninspectable callables (C extensions) and
signature arity checks for `*args` callables or `Callable[..., R]`.

## Auto-binding

`fn: Class.method` without kwargs instantiates `Class()`; if that needs arguments, the error
prints a ready-to-paste dict example with the constructor parameters. Owning-class detection
uses `__qualname__`, so it cannot work for lambdas or nested scopes.

## Round-trip

`class:` and `call:` results get the original spec stamped as `__confarg_spec__` (best effort:
some objects refuse attributes), which is how `dump()` reproduces them. Partials dump as
`{fn, bind}` or a bare path; functions as their dotted path. A callable not built by confarg
and without `__module__`/`__qualname__` cannot be serialized.

## CLI

Plain openers are registered statically; bind and factory parameters are discovered from
the named target at `populate_*` time ([04](04-cli-adapters.md#static-and-dynamic-flags)).
In `class` mode constructor params are `--f.<p>` and `__call__` params are `--f.bind.<p>`;
in `fn: Class` mode constructor params are bind targets. A former implicit form, where a
bare return type triggered collection of sibling flags, was removed.
