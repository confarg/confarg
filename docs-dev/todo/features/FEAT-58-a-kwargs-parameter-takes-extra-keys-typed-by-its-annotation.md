---
filed: 2026-10-26  # split out of FEAT-2, filed 2026-09-12
where:
  - src/confarg/_callable.py::_coerce_kwargs
  - src/confarg/_callable.py::_fillable_params
  - src/confarg/_types.py::_init_fields
effort: L
needs_design: true  # whether a struct's **kwargs stays a member named kwargs, and how argv and help spell an extra key
risk: medium
impact: config  # a struct's `kwargs:` key would change meaning if extra keys became its spelling
severity: critical  # an argv token reaches a `**kwargs: int` parameter under args as a str, with no error
---

# FEAT-58 — A `**kwargs` parameter takes extra keys, typed by its annotation

The two routes into one signature read `**kwargs` differently.
Under the `args` of `bind:` or `call:`, an extra key binds as a keyword argument, but its value is not typed by the annotation: with `def f(a: int, **kwargs: int)`, `--f.bind pkg.f --f.args.a 1 --f.args.b 2` builds a partial whose keywords are `{'b': '2'}`, a string.
A struct reads its `__init__`'s `**kwargs` as a member named `kwargs`, typed: `{class: pkg.K, a: 1, b: '2'}` is refused, `Unknown field(s) ['b'] for K at 'k'. Valid fields: ['a', 'kwargs']`, while `{class: pkg.K, a: 1, kwargs: {b: '2'}}` reaches the annotation, `Cannot coerce str '2' to int at 'k.kwargs.b'`.

The design pass decides one reading for both: whether extra keys beside the named parameters are the spelling of `**kwargs` (as a call site writes it, and as jsonargparse's `init_args` does *(inferred)*), how each is typed and validated, how argv registers and completes a key no signature names, and how the dump writes them back.
[BUG-240](../bugs/BUG-240-a-var-positional-parameter-cannot-be-set-under-args.md) is the `*args` side of the same question, and [FEAT-50](FEAT-50-a-kwargs-forwarded-to-the-parent-sets-its-members.md) a `**kwargs` forwarded to a parent's constructor.
See [callables](../../architecture/callables.md).
