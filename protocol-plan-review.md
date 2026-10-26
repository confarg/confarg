# Review — the Protocol-typed fields plan

**Reviewed:** [docs-dev/todo/plans/protocol-typed-fields.md](docs-dev/todo/plans/protocol-typed-fields.md) (amended 2026-10-26) · **Reviewed against:** the code at `src/confarg/` as of `wzmwqsyu`, the architecture notes, the tickets it cites, and the runtime behavior of Python 3.12.11.

The plan is unusually thorough: every decision names its rejections and precedents, the four-question `_conformance` leaf is the right seam, `_tagged_struct` stays the decision-maker, and the verification list is written as tests against the `loader` fixture.
The findings below are what it missed.
Two are behavior bugs in the making (1, 2); the rest are sequencing gaps, an unhandled member shape, unrecorded limitations, and factorization opportunities.

## Runtime claims, verified

I checked the plan's version-sensitive claims on 3.12.11; all hold:

- `__protocol_attrs__` exists on 3.12 (`{'greet'}`, `{'greet', 'name'}`) and excludes `__init__` (a Protocol defining `__init__` answers `set()`).
- `typing._no_init_or_replace_init` exists, `Greeter.__init__` and `Impl.__init__` (a nominal implementer with no `__init__` of its own) are identical to it, and the first instantiation replaces `Impl.__init__` with `object.__init__` — the plan's keying on the function, not on `is_protocol(cls)`, is right, and both states give `{}`.
- `typing_extensions.Protocol` classes set both `_is_protocol` and `__protocol_attrs__` on 3.12, so the fallbacks reach them — but see finding 10.

## Findings

### 1. HIGH — the dump of a conforming non-struct value writes `{}`, which does not read back

The plan's own decision "a conforming class that is no struct is built as under `Any`" (so `{class: uuid.UUID, hex: ...}` builds, a `str`, an `Enum` or a registered leaf can conform), but its dump story covers only struct implementers: "`_serialize_struct` writes the implementer's tag through its `_tagged_struct` branch".

That branch is guarded (`src/confarg/_serialize.py:486`):

```python
bound = _tagged_struct(actual_tp, tp) if actual_tp is not _class_of(tp) and _is_struct(actual_tp) else None
```

For a value whose class is no struct — `builtins.str` conforms to a Protocol declaring `upper`; `_is_struct(str)` is `False` — `bound` is `None`, and the function then writes `_struct_state_fields(proto)`, which for a Protocol is empty.
`dump()` writes `g: {}`, silently, with no tag and no foreign-value warning.
Reading it back is refused, since the Protocol demands its tag: exactly the invariant "[a written file holds what its reader reads back](docs-dev/architecture/design-decisions/a-written-file-holds-what-its-reader-reads-back.md#a-written-file-holds-what-its-reader-reads-back)" broken, and worse than BUG-294, which at least warns.

In a union it is the same: `_variant_holds`'s new `instance_conforms` arm picks the Protocol variant for the value, and `_serialize_union` then hands it to `_serialize_struct` with the same result.
The plan's `uuid.UUID` example happens to work because `UUID`'s constructor signature reads, so it is a plain class; a Protocol that `str`, `int`, `bool`, an `Enum`, a `PurePath` or a registered leaf satisfies is the reachable case (FEAT-59 exists precisely because such Protocols are common).

**Suggestion:** decide the form for a conforming non-struct value before step 3 lands: either the `Any`-node form (`{class: <path>, <the spec `_serialize_any` spells>}`, via `_held_object_form`) plus the tag, or a foreign-value write with its warning when no spec spells it.
Add the row to the verification list: "the dump of a Protocol field holding a conforming non-struct value reads back".

### 2. HIGH — a `class:` naming a Protocol class under a non-Protocol declared type still escapes raw

The plan refuses a Protocol class at the tag, in `class_conforms`, "so the tag and `type[P]` share it".
But `class_conforms` is asked only where the *declared* type is a Protocol.
Where it is not, a Protocol class sails through every check and dies at the call:

- under `Any`: `{class: pkg.Greeter}` → `resolve_held_spec` → `_instantiate_class_spec` → `Greeter()` → `TypeError: Protocols cannot be instantiated`;
- under a plain class or ABC field: `class ProtoImpl(SomeABC, Protocol)` passes `issubclass` in `_tagged_struct` and instantiates the same way;
- under `type[X]`: `_coerce_type_ref`'s `issubclass(obj, constraint)` passes when the Protocol inherits `X`.

jsonargparse 4.53 refuses a protocol at `class_path` wherever it meets one ("Expected an instantiatable class, but protomod.Greeter is a protocol"), not only under Protocol-typed targets.
The plan's own reasoning — "construction would then escape as `TypeError: Protocols cannot be instantiated`" — applies verbatim here, and BUG-269 (a constructor's own exception escapes raw) will not cover it: this is a class confarg could refuse before calling.

**Suggestion:** the refusal wants a home in the one constructor every named class goes through — `typedload._construct.construct_named_class` (or `build_from_nothing`, which BUG-215 already made the "a class a tag or an opener named" refusal's home) — answering "may this class be built?" with `is_protocol`.
That is the canonical-function placement, and it covers the tag, `type[P]`, the `Any` node and a Callable's `class:` at once.
Add a verification row for `{class: pkg.Greeter}` under `Any`.

### 3. MEDIUM — an `@overload` stack is a member whose last `def` is a trivial body

The member-shapes section reads the *signature* of an overloaded Protocol method from "the last `def` of the body" — correct for the expected signature.
But the trivial-body rule says "a member a class finds only on a Protocol class in its MRO counts unless its body is trivial", and the last `def` of an overload stack is a `...` stub:

```python
class Loader(Protocol):
    @overload
    def load(self, x: int) -> int: ...
    @overload
    def load(self, x: str) -> str: ...
    def load(self, x): ...  # the implementation stub — trivial
```

Read naively, `Loader.load` is a trivial-bodied member found on a Protocol class, does not count, and *every* implementer is refused.
The rule needs an explicit carve-out: a member decorated with `@overload` (or followed by one — the stub carries the final `def`) is a member, whose expected signature the plan already settles.
`typing.get_overloads` is how the descriptor decision already reads overload sets (`_descriptor_input`, in [introspection](docs-dev/architecture/types/introspection.md)), so the precedent is in-repository.

The neighboring case is unrecorded too: `@abstractmethod` with a *non-trivial* body (a real default implementation kept abstract).
The plan's rule counts it (non-trivial body), so `class Inherits(Abs): pass` is accepted and works at runtime, where mypy refuses it (abstract).
That is a defensible choice — the body is real — but it belongs in limitations beside the `Partial` row, since the plan records every other checker disagreement.

### 4. MEDIUM — the trivial-body verdict is per-Protocol data, and the plan gives it no home in the cache

`protocol_members` is cached per Protocol, `class_conforms` per (class, Protocol) pair.
The trivial-body rule, the four ordering methods and the member-kind split (method vs data) are all properties of the *Protocol* alone, but the plan's wording of `protocol_members` ("which members must an implementer have, and which are methods?") is `typing.get_protocol_members`'s raw answer.
If `class_conforms` re-derives exclusions and kinds per pair, the `ast` source read repeats for every candidate class under the Protocol — the subclass scan asks `_tagged_struct`, hence `class_conforms`, of every nominal implementer, and the type walk of every field.

**Suggestion:** make `protocol_members`'s cached answer the *effective* member map — name → kind (method / data), with trivial-bodied stubs and the `object`-only members excluded, and the ordering four marked — computed once per Protocol, including the one `ast` walk of its source.
`class_conforms` then holds only the pair-level logic (the call-shape walk, the reason-as-data).
This is also where finding 3's overload carve-out lives.

### 5. MEDIUM — BUG-293 is a dependency of FEAT-57's step 3, but the plan asks only for its design pass first

Phase 2 says BUG-293's "design pass decides whether `_accepts` and `_holds` become one predicate, and FEAT-57 then writes its Protocol branch once, in that predicate".
For FEAT-57's step 3 to write its branch *in that predicate*, the predicate has to exist — which is BUG-293's implementation, not its design pass.
The FEAT-57 ticket says `blocked_by: [BUG-291, BUG-293, BUG-294, BUG-295]`, so the intent is clear, but the plan's phase text lets a reader sequence "design BUG-293, then build FEAT-57" and land on a rebase exactly the kind the plan is trying to avoid.
Say so: BUG-293's fix lands before FEAT-57's step 3, the design pass just decides its shape.

### 6. MEDIUM — the `Callable[..., P]` factory check shares the `type[P]` data-member hole, and the limitation is recorded for only one of them

`_unproducible_return` is rewired to `class_conforms` "when that annotation is a Protocol" — the methods-only half, since no instance exists yet.
The plan records "a `type[P]` field does not check data members" in limitations, but the same false acceptance arises for a bare class path under `Callable[..., Named]`: a class whose `greet` conforms but whose instances never set `name` is accepted as a factory, and every product silently fails the data member.
Record the limitation for both, or restrict the rewiring to callback Protocols (where `class_conforms` is complete, `__call__` being the only member) and refuse struct-like Protocol returns as uncheckable — the plan should pick one and say which.

### 7. LOW — the message generalization names one factory; the tag site uses another

The plan generalizes `not_a_subclass` ("is not a subclass of" becomes "does not implement").
The tag site raises `TypeCoercionError.tag_not_a_subclass` (`src/confarg/exceptions.py:841`, raised from `typedload/_construct.py:1765`), a different factory with the same clause plus "Supply the class's fields as keys beside the tag" — it needs the same rewording, and `_construct_by_class_path`'s `parent` spelling (`repr(tp)` for a parameterized field) needs deciding for a Protocol `tp`.
Name both in the plan so the wording is settled once, not discovered per site.

### 8. LOW — step 1 leaves the synthetic `args`/`kwargs` members live in `--help` and the type walk

Step 1 rewires `_tagged_struct`, `_coerce_type_ref`, `_unproducible_return` and the subclass scan; the `_constructor_parameters` reading that empties a Protocol's fields lands in step 2.
Between the two, `_struct_fields(Greeter)` still answers `{'args', 'kwargs'}`, so `--help` of a Protocol field advertises `--g.args` and `--g.kwargs`, `${g.args}` resolves, and a custom `union_tag="args"` is shadowed by a member that is about to stop existing.
Nothing breaks — the tests are per-step — but every step description should name its intermediate state, and moving the `_constructor_parameters` reading into step 1 (it is a one-line identity check the plan has already settled) makes no step ever surface the synthetic members.
Consider it.

### 9. LOW — BUG-291's refusal loses the parameter types, and its expected signature is unsettled for `ParamSpec`

The current message names the expected types: "annotation expects 1 parameter(s) ['int']".
`call_conforms` leaves types out by design, and `Callable[[int], int]` has positions, not names — so the new refusal must decide what it names (positions and kinds, presumably: "expects (int, /), but 'kw_only' takes its first parameter by keyword only").
The plan's reason-as-data says "the parameter that does not fit" without settling the spelling; the wording tests in the verification list should pin it.

Separately, the plan settles the expected signature for `Callable[[A, B], R]`, `Callable[..., R]` and a callback Protocol, but not for `Callable[Concatenate[int, P], R]` — which `_callable_param_types` today reads as a flat parameter list, so the count check silently treats `int` plus the ParamSpec as two fixed parameters.
Whatever the new home answers for it (probably "check nothing", as for `...`), it should be said, or the BUG-291 rewrite changes behavior for ParamSpec callables by accident.

### 10. LOW — `typing_extensions` Protocols: compatible, but untested

`typing_extensions.Protocol` classes set `_is_protocol` and `__protocol_attrs__` on 3.12 (verified), and `typing.is_protocol` reads the same attributes on 3.13+, so the plan's predicates reach them.
But many libraries' Protocols come from `typing_extensions`, the private names the plan keys on are `typing`'s, and the plan pins its version-sensitivity tests only across CPython versions.
Add a verification row: a `typing_extensions.Protocol` field behaves as a `typing.Protocol` one, on 3.12 and 3.13+ alike. jsonargparse's Protocol support covers both spellings.

### 11. LOW — an `async def` member conforms by shape

`async def greet(self) -> str` on an implementer passes the call-shape check (the signature reads the same) and the member-presence check, but calling it yields a coroutine where the Protocol promises a `str` — every type checker refuses it.
The plan records the milder checker disagreements (a method stored on the instance, a method where a data member is declared); this one belongs in the same limitations line, or in the member-shape section as a refused kind (`inspect.iscoroutinefunction` mismatch with the expected side).
At minimum, record it.

### 12. Factorization — the struct-like vs callback split is derived in two places

FEAT-2 moves two predicates together — `_is_plain_class` answering `False` and `_is_callable` answering `True` for a callback Protocol — and the plan says so, but the shared fact ("this Protocol's only member is `__call__`") has no named owner: `_is_plain_class` will derive it from `protocol_members`, `_is_callable` will derive it again, and `_variant_holds`'s CALLABLE arm will need the same answer for `instance_conforms`.
The shape-dispatch invariant is that the predicates stay canonical and the table owns the order; three derivations of one fact is the drift the invariant exists to prevent.
Give `_conformance` a third small question — `callback_shape(proto)` or an answer folded into `protocol_members`'s effective map (finding 4) — and let the two `_types` predicates read it.

### 13. Verification gaps

Rows the plan's own decisions make reachable but its verification list does not name:

- the dump of a conforming *non-struct* value, in a plain field and in a union (finding 1);
- `{class: pkg.Greeter}` under `Any` and under a plain class field (finding 2);
- an `@overload`ed Protocol method (finding 3), and `@abstractmethod` with a body;
- a Protocol named with a custom `union_tag` its nominal implementer shadows, *inside a union* — `_demands_tag` answers no there, and the structural match of a no-field variant against `{}` (it matches: `_structurally_matches` requires only `keys ⊆ fields`) is the ambiguity BUG-295's predicate has to keep out for the shadowed spelling too;
- a `typing_extensions.Protocol` (finding 10);
- `Callable[..., P]` with a struct-like `P` and a bare class path (finding 6);
- a Protocol whose member is provided by the implementer as a `property` where the Protocol declares a *method* (the plan settles the non-callable `greet = 3` case; a property is the spelling a reasonable user writes, and it should be refused for the same reason — `callable(property)` is `False`).

## SOLID and the project invariants

- **Single responsibility / interface segregation:** the four-question `_conformance` leaf is clean, and `_conformance` importing the standard library only, with reasons as data so `exceptions` stays out, is the right cycle-free seam.
  One wrinkle: `class_conforms` carries the Protocol-class refusal, a *buildability* policy, inside a *conformance* answer — justified (the tag and `type[P]` share it, and no caller wants the split), but it makes `class_conforms` mean "conforms and may be built"; say that in its docstring, because finding 2 shows the policy has claimants outside `_conformance`'s asker list.
- **Open/closed:** no new `_TypeKind` is introduced; each affected `match` arm gains its Protocol branch, which keeps "each match lists every kind" intact.
  The scattered `is_protocol` checks are the price, and findings 4 and 12 are the containment.
- **Liskov substitution:** n/a (no inheritance in the design).
- **Invariants:** "delegate to the canonical function" is respected — `_tagged_struct` stays the decision-maker, `_demands_tag` is named for the question, messages live on `exceptions`, caches are weak per class.
  The two violations in the making are finding 1 (a dump that does not read back) and finding 2 (a raw `TypeError` the plan's own rationale says to refuse), both of which are fixable inside the plan's structure rather than by redesign.
- **Documentation protocol:** the plan complies with feature-design's parity mandate (every row tested through the `loader` fixture, messages spelled per channel) and with working-with-architecture's recording rules; the limitations list it plans needs findings 3, 6 and 11 added to it.

## What I would do before implementation starts

Nothing here unsettles the plan's decisions — the conformance rule, the tag-demand, the call-shape checker and the phase order all survive scrutiny.
Before step 1 of FEAT-57: fold finding 4 into `protocol_members`'s contract, settle finding 3's overload rule, and add finding 2's guard to `construct_named_class` (it is BUG-291-adjacent, small, and closes every remaining raw `TypeError: Protocols cannot be instantiated` in one place).
Findings 1 and 5 want a paragraph in the plan each; the rest want rows in the verification list and lines in the future limitations entry.
