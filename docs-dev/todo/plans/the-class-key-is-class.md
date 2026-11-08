# Plan — The class key is `class`

**Drafted:** 2026-11-03 · **Status:** approved · **Tickets:** [REF-121](../refactors/REF-121-drop-the-union-tag-option.md), closing [BUG-285](../bugs/BUG-285-a-shadowed-tag-warning-at-a-struct-root-names-the-key-root.md) and [REF-95](../refactors/REF-95-the-tag-collision-tests-leave-their-warnings-uncaptured.md)

`union_tag` was introduced when the discriminator was confarg's only reserved key, and it is now the only one a caller can rename.
`classfn`, `bind`, `call`, `args`, `__include__`, `__cast__`, `__value__`, `__root__`, the list ops' spellings and the locals namespace are all fixed.
Since BUG-305 the tag is the class opener of every spec ([the union tag is the class key in every role](../../architecture/design-decisions/the-union-tag-is-the-class-key-in-every-role.md#the-union-tag-is-the-class-key-in-every-role)), so a custom tag renames one opener of four:

```yaml
# union_tag="kind"
model: {kind: pkg.Mul, factor: 3}      # the class opener, renamed
loss:  {classfn: pkg.Loss.from_name}   # its sibling, not
```

The option costs about 960 mentions across 29 modules, since it is threaded per call through every layer.
It also costs `check_union_tag`, which keeps the tag off every key another role already spells, and the limitation that `union_tag="type"` imports whatever a `type` entry under an `Any` names.
On top of those comes a whole family of rules for a field spelled like the tag: real field wins, the shadowed-tag warning, the subclass-only owner, and the dump writing no tag over an owner (BUG-92, 97, 102, 103, 106, 276, 285, 302, 303).

The design was settled with the maintainer on 2026-11-03.

## Decisions taken

### The option goes from every entry point

`union_tag` leaves `MergeOptions` (so `load()`, `merge()` and every adapter), `_defaults._Options`, `build()`, `from_dict()`, `resolve()`, `dump()` and `dump_file()`.
Passing it raises the `TypeError` any unknown keyword raises.
confarg has not shipped, so there is no deprecation period and no alias.

The key is `_defaults.CLASS_KEY = "class"`, beside `BIND_KEY`, `CALL_KEY`, `CLASSFN_KEY` and `ARGS_KEY`.
`UNION_TAG` and `check_union_tag` are deleted, since nothing is left to check.
`_callable.openers(union_tag)` and `object_openers(union_tag)` become the constants `OPENERS` and `OBJECT_OPENERS`, which keeps the single answer BUG-305 gave to "which keys open a spec".

Precedents: config languages fix their key.
Hydra and detectron2's LazyConfig use `_target_`, jsonargparse uses `class_path`, and the mmcv and AllenNLP registries use `type`; none of them can be renamed.
Serialization libraries make the tag configurable (serde's `#[serde(tag = …)]`, msgspec's `tag_field`, pydantic's `discriminator`), but per type, never per call.
There the tag is a data field that only selects among a union's members, and never opens a callable spec.
confarg's key opens a Callable's and an `Any`'s spec, which have no type to hang a per-type option on, so confarg belongs to the first family.

Rejected:

- **Keep the option for a foreign format whose discriminator is spelled otherwise**, the reason recorded in BUG-305 (maintainer-chosen).
  An mmdet-style `{type: ResNet, depth: 50}` is no longer read as it stands; the caller renames the key before `build()` or `from_dict()`, as a Hydra user does to reach `_target_`.
  The renaming moves to [limitations](../../architecture/limitations.md) as what the library cannot do.
- **Configure it per type**, as msgspec and serde do.
  It fits a union of structs, but not the opener of a lone `Callable` or `Any`, which has no class of its own to carry the option.
- **A process-wide setting.**
  It is global state: two libraries in one process configuring with confarg would disagree.

### The shadowed-tag machinery goes with it

No struct confarg reads can own a member spelled `class` (run on 3.12):

```text
make_dataclass("D", ["class"])          -> TypeError: Field names must not be keywords: 'class'
namedtuple("N", ["class"])              -> ValueError: Type names and field names cannot be a keyword: 'class'
NamedTuple("N", [("class", int)])       -> ValueError: Type names and field names cannot be a keyword: 'class'
attrs.make_class("A", {"class": ...})   -> SyntaxError in the generated __init__
inspect.Parameter("class", ...)         -> ValueError: 'class' is not a valid parameter name   (a plain class is read by its signature)
TypedDict("T", {"class": str})          -> accepted, but a TypedDict is no struct yet (FEAT-45)
```

A Protocol's members come from its class body, which cannot spell `class` either.
So `_types._union_tag_shadowed(tp, "class")` always answers `False`.
It is deleted, and each caller keeps the branch that `False` takes:

- `_construct`: the ambiguity remedy for an owned tag, the subclass-only owner (`_construct_struct`'s BUG-103 path), the union's owned-tag refusals, and `_warn_shadowed_tag_key`.
- `_default_layer`, `_naming`, `_typed_merge`, `_tags` (both the merged tag and the argv scan), `_serialize`'s tag writer and its warning, and `cli._build`'s three registration checks.
- `ConfargWarning.tag_shadowed_by_member`, and the "can be changed via the union_tag= parameter" message.

A dict variant holding `class` as data where no tag selects (BUG-276) is not shadowing: it never asked `_union_tag_shadowed`, and it stays.

Rejected: **keep the machinery dormant until FEAT-45**.
Nothing reachable would exercise it, so its tests could only call internals.
FEAT-45 carries the question instead: a TypedDict key spelled `class` is the one way back, and its design pass chooses between refusing that key, the way Hydra and jsonargparse reserve theirs everywhere, and bringing real field wins back for it.

### "Union tag" becomes "class key"

The term leaves the code, the messages and the notes for "class key".
Identifiers follow: `UNION_TAG` becomes `CLASS_KEY`, and helpers named for the tag (`_construct`'s `_union_tag_*`, `_parse_cli`'s tag-at-fallback test) are renamed as they lose their parameter.
Almost every line naming the term already changes when the parameter goes, so the rename adds little to the diff.

Rejected: **keep "union tag" internally.**
It means less churn, but two names for one key, and the internal name describes the narrowest of its four roles.

## Build order

One revision.
Every step leaves `ty` reporting the call sites still to change.

1. `_defaults`: add `CLASS_KEY`, and delete `UNION_TAG`, `check_union_tag`, `MergeOptions.union_tag` and `_Options.union_tag`.
   In `_callable`, `openers` and `object_openers` become constants.
2. Delete `_union_tag_shadowed` and fold each caller as listed above, then delete the warning and its factory.
3. Remove the `union_tag` parameter from every function, top down from the public entry points, reading `CLASS_KEY` where the value was read.
   The adapters receive it through `_Options` only (`cli/_sources`, `cli/_collect`, `cli/_build`, each front-end's `_register`, `_context` and `_completion`).
4. Rename identifiers, docstrings and messages, "union tag" to "class key".
5. Tests:
   - Delete the tag-collision suites.
     These are `TestUnionTagFieldCollision` in `tests/test_cli.py` and `tests/cli/test_backend_contract.py`, `TestEnvSubclassOnlyTagCollision`, `TestTagFieldCollision`, the shadowed tests of `tests/test_tags.py`, every test built on a `Kind` or `kind` field, and the `check_union_tag` tests BUG-305 added.
   - Rewrite under `class` the tests that ran a custom tag for another reason, such as `type` or `kind` reaching a Callable, an `Any` or a CLI path.
     Drop the redundant `union_tag="class"` from the rest.
6. Notes:
   - Retire the custom-tag decisions:
     - `union-tag-defaults-to-class.md` becomes `the-class-key-is-class.md`, with the keyword rationale, the decisions above, and their rejected alternatives.
     - `the-union-tag-is-the-class-key-in-every-role.md` keeps its rule, one key in every role, and loses the custom tag, "A tag spelling another role is refused" and its Cost paragraph.
     - `a-shadowed-tag-warns-on-use.md` is deleted.
     - `real-field-wins.md` keeps the casts and the locals, without the tag.
     - The README rows follow.
   - Sweep the other notes naming the option: `callables`, `invariants`, `limitations`, `types/construction`, `types/serialization`, `pipeline/api-seams`, `cli-parsing/casts-and-reserved-words`, the three `cli-adapters` notes, `a-named-tag-is-imported-before-registration`, `an-explicit-tag-opts-a-leaf-back-in` and `class-names-the-type-it-builds`.
     Also sweep the glossary's class-key entry.
7. Boards and plans:
   - Delete BUG-285 and REF-95.
   - Re-score BUG-306 from its reproduction, since the workaround its severity cites is gone.
   - Reword the tickets and plans whose text or reproduction passes `union_tag`: BUG-283, BUG-286, FEAT-10, FEAT-15, FEAT-22, FEAT-47, REF-42, REF-58, REF-71, `protocol-typed-fields`, `a-protocol-reads-the-scalars-that-satisfy-it` and `untyped-config-rewriter`.
   - Run `docs-dev/todo/index.py`.

## How to tell it worked

- `grep -rn union_tag src tests docs` finds nothing.
  In `docs-dev/architecture/` it finds only the rejected alternatives of `the-class-key-is-class.md`.
- The full suite, `ty check` and pre-commit pass, and the touched tests pass on 3.13 to 3.15.
- A full run prints no `ConfargWarning`, now that the 34 REF-95 counted are gone.
  If so, REF-95's `filterwarnings = ["error::confarg.exceptions.ConfargWarning"]` gate lands in the same revision; if another test still leaks one, that is filed apart.
- `load(Cfg, union_tag="kind")` raises the unknown-option `TypeError`, and `build(Cfg, {}, union_tag="kind")` raises Python's unexpected-keyword one.
