# Bind yields a partial of its target

`bind:` is an opener: `{bind: T, args: {<args>}}` is a `functools.partial` of `T` with `args` applied, [by position where they can](../callables.md#arguments-go-by-position-where-they-can), its target a dotted path or a callable spec of its own, and the mapping under `args` the target's arguments ([a computation's arguments nest under args](a-computations-arguments-nest-under-args.md#a-computations-arguments-nest-under-args)).
`{bind: T}` with no argument is the bare `"T"`, so a string and its dict form are still one spec.
The `fn:` opener and the `bind:` kwargs dict (`{fn: T, bind: {a: 1}}`, `{class: H, bind: {p: 2}}`) are removed outright, with no deprecation period and no dedicated error: `fn` is an ordinary key, and a dict under `bind:` is read as a target spec, so the old forms fail the way any spec without an opener, or with two, already does.

Why: with `bind` as a directive beside the target, a spec had two namespaces of arguments, the siblings (constructor arguments of an owner under `fn:`, of a class under `class:`, of the function under `call:`) and the `bind:` dict, and which one an argument belonged in depended on the opener.
Making `bind` the opener left one rule for all three: a sibling of the opener was an argument of its target, until the arguments of `bind:` and `call:` moved under `args`.
A partial over an instance is no longer a second dimension of `class:` but a `bind:` whose target is the `class:` spec, which composes the forms instead of multiplying them.

Rejected:

- **A deprecation period for `fn:` and the `bind:` kwargs dict.** confarg has not shipped, so there is no installed configuration to protect.
  Keeping the old dict beside the new target would also make `bind: {…}` ambiguous, a kwargs dict or a target spec told apart only by whether it holds an opener, and every channel and front-end would carry that heuristic for a release.
- **A migration error naming the replacement for `fn:`.**
  It would keep `fn` reserved, so a parameter named `fn` would need a spelling of its own, for the sake of configurations that do not exist yet.
- **A migration table from the old forms in the user documentation** (FEAT-34, declined in that part).
  The same ground: confarg has not shipped, so no user has an old configuration to migrate, and the tutorials teach the grammar as it is.
- **`{bind: T}` always a partial, as Hydra's `_partial_: true` is.**
  It would make the dict form and the bare string resolve to different objects for a function (`partial(f)` against `f`), and the shorthand rule that opens `"T"` into `{bind: T}` before an argument refines it would change the value of a field that an argument only refined.
- **A target dict restricted to `classfn:`.**
  It would leave the partial over a callable instance with constructor arguments without a spelling; any callable spec as a target covers it, and `classfn` becomes one more opener such a target may hold.

Precedent: Hydra's `instantiate` keeps `_target_` and its arguments in one mapping and asks for a partial with `_partial_: true`, so arguments are never nested under the partial marker; `functools.partial` itself takes the callable first and its keywords beside it.

Cost: a configuration written with `fn:` or a `bind:` kwargs dict must be rewritten, and an instance method whose owner needs constructor arguments has no spelling but a `call:` of a factory until `classfn:` names one.
