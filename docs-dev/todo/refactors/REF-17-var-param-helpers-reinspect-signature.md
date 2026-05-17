# REF-17 — `_var_param_names` / `_var_positional_name` / `_var_keyword_name` re-inspect the same signature

**Where:** `src/confarg/_types.py` · **Filed:** 2026-09-13
**Effort:** S · **Risk:** low · **Impact:** none

Three helpers each independently call `inspect.signature(tp.__init__)` and walk parameters for
`VAR_POSITIONAL` / `VAR_KEYWORD` (`_var_param_names`, `_var_positional_name`, `_var_keyword_name`).
`_construct.py` calls two of them back-to-back at lines 368-369. Replace with a single
`_var_params(tp) -> _VarParams(pos_name, kw_name)` (both `None` for dataclasses) that inspects once;
`_construct.py` then reads `vp = _var_params(tp)`. Removes ~25 lines and one redundant inspection
per struct construction.
