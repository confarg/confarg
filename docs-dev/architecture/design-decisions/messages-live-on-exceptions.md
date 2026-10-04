# A user-facing message lives on the exception that raises it

An error message raised from **more than one site** is built by a classmethod factory on its
exception class, not by an f-string at each of them. `InvalidConfigFileError` and `LocalsError`
were written that way from the start; `ConfargError.root_cast_not_object`,
`ConfargError.include_siblings_need_a_dict` and the three `UnknownArgumentError` factories
followed once the duplication had cost something (REF-51, closed). The two construction-error
families in `typedload/` followed before they could drift a second time (REF-69, closed):
`TypeCoercionError.wrong_shape` for the six shape refusals, `TypeCoercionError.not_a_subclass`
for the three class-tag refusals, and a `none_sentinel` keyword on `cannot_coerce` carrying
the none-word remedy. The per-variant breakdown of the two ambiguity refusals is the one
multi-site text that stays out of `exceptions.py`: it reads `_struct_fields` and
`_struct_defaults`, so it lives as one module-level builder in `_construct.py`, parametrized
by its header and remedy lines. The threshold is duplication,
not user-facing-ness: a message with one call site is fine where it is raised, and most of them
still are. The point is not tidiness either — a message spelled at four call sites drifts, and
the drift is invisible because no test reads more than one of them. Two of the four "Unknown
argument" spellings had already lost the quotes around the flag, so the same failure printed
`'--foo'` or `--foo` depending on which branch of `_parse_cli` noticed it.

Where such a message reaches a user, the flag is **quoted** — `Unknown argument: '--no-value1'`.
That matches the messages beside it (`Missing value for '--value1'`) and cyclopts; argparse and
click leave it bare, and the divergence from them is deliberate, since confarg's flag paths are
dotted and a bare `--db.hosts.0-` at the end of a sentence is hard to see the end of
(maintainer-chosen).

The constraint on the factories is that **`exceptions.py` imports nothing from `confarg`**.
`dictexpr` is allowed to depend on the standard library and this one module, and no more
([README § Source map](../README.md)), so an import here would pull the type machinery into
`dictexpr`'s closure. A factory therefore cannot reach `_src_type` or `dotted_name`: either the
caller formats the piece and passes it in, or — as for `root_cast_not_object`, whose value is
always JSON the cast has just decoded — the argument provably cannot be a token and `type()`
names it correctly unaided. Holding that line is why `_locals_file_flag` is a module-level
helper in `exceptions.py` rather than a call into `cli`.
