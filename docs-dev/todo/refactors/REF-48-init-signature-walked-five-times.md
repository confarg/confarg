# REF-48 — `inspect.signature` is walked four or five times per struct

**Where:** `src/confarg/_types.py` (`_is_plain_class`, `_init_fields`, `_init_defaults`,
`_var_params`), `src/confarg/typedload/_construct.py` (`_call_with_var_positional`) ·
**Filed:** 2026-09-24
**Effort:** M · **Risk:** high · **Impact:** none

`_init_fields`, `_init_defaults` and `_var_params` are the textbook three functions differing only
in *which attribute of each `inspect.Parameter` they collect*; `_call_with_var_positional` walks
the same parameters a fourth time for the positional-fillable names, and `_is_plain_class` a
fifth just to ask whether any parameter other than `self` exists. One
`_init_params(tp)` record — fields, defaults, var-positional, var-keyword, positional names —
replaces all of them, and `_var_params` is already canonical for "which `__init__` parameters are
`*args` / `**kwargs`?"
([09-invariants.md](../../architecture/09-invariants.md)), so the record is where that answer
belongs.

The same pass should add `lru_cache` to `_dc_fields`, `_init_fields`, `_namedtuple_fields` and
`_var_params`: `get_type_hints` currently re-runs on every field access, and one union
disambiguation calls `_struct_fields` at least twice per variant before `_construct_struct` calls
it again. Also: the `{name: type}` + `{name: default}` to required-set derivation is spelled three
times in `_construct.py`.

While in `_call_with_var_positional`: its loop (`_construct.py:362-382`) hand-rolls the
positional binding that `inspect.Signature.bind_partial` plus `BoundArguments.args`/`.kwargs`
already does. The hand-rolled version appends to `pos_args` without checking that every *earlier*
parameter was also filled, so a gap — `__init__(self, a=1, b=2, *rest)` given only `b` — would
pass `b`'s value into `a`. That is unreachable today, because `_construct_struct`
(`_construct.py:396-415`) fills every declared field before the call, so take it as a robustness
and clarity win rather than a live bug. One behavioural difference to accept deliberately:
`bind_partial` raises `TypeError` on a name the signature does not accept, where the current code
forwards it to `tp(**kwargs)` and lets CPython raise a differently-worded `TypeError`.

Two hard exclusions, to be written into the code as comments:

- `_dc_defaults` calls `default_factory()` and must **never** be cached — a cached mutable default
  would be shared between constructed objects;
- nothing that reads `_LEAF_COERCIONS` may be cached (`_is_registered_leaf`, `_is_struct_variant`,
  `_is_eagerly_coercible`), because `register_leaf_type` mutates it at runtime
  ([05-types-and-construction.md#leaf-coercion](../../architecture/05-types-and-construction.md#leaf-coercion)).

Risk is **high**: this is the introspection every channel and front-end builds on, and a caching
mistake is silent until someone registers a leaf type or mutates a default.
