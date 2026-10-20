---
filed: 2026-10-20
where:
  - src/confarg/typedload/_coerce.py::_try_coerce
  - src/confarg/typedload/_coerce.py::read_as_object
  - src/confarg/typedload/_construct.py::read_union_leaf
  - src/confarg/_pipeline.py::below_argv
  - src/confarg/cli/_build.py::_collect_loop_typed_specs
  - src/confarg/_serialize.py
effort: M
risk: medium
impact: none
severity: trivial  # a bug if the inferred race is observed
inferred: true  # the race is read off the documented behavior of catch_warnings; never reproduced
---

# REF-108 — The library steers by process-wide warning filters

Seven `with warnings.catch_warnings():` blocks sit in library paths, most of them added by the fixes for BUG-154, BUG-230, BUG-233 and BUG-234: `_coerce.read_as_object` and `_construct.read_union_leaf` silence `FloatOverflowWarning` on every leaf an expression reads, `_coerce._try_coerce` turns it into an error on every token a parser coerces, `_pipeline.below_argv` and `cli/_build._collect_loop_typed_specs` silence everything during registration, and `_serialize` records and replays in two places.

`catch_warnings` swaps the module-global filter list, and Python documents it as not thread-safe before 3.14's context-aware warnings: a `confarg.load` on one thread changes what another thread's warnings do while it runs *(inferred)* — `_try_coerce`'s `simplefilter("error", FloatOverflowWarning)` would turn a concurrent construction's overflow warning into an exception there.
`_try_coerce` also uses the filter as control flow: it raises the warning as an error, catches it, recomputes `float(token)`, and warns again under the flag's spelling.

Fix direction: say what the caller wants instead of filtering what was emitted — `_coerce_float_value` takes a `warn` callback (or returns whether it overflowed), so the reading passes a no-op, `_try_coerce` passes one naming the spelling, and construction keeps `warnings.warn`; registration's silencing collects into a list it drops.
The read-side pair also repeats the same three lines, which the callback removes.
