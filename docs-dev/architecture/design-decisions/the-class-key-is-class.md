# The class key is `class`

The key that names the class to build from the keys beside it is `class` (`_defaults.CLASS_KEY`), in every role it plays ([one class key in every role](one-class-key-in-every-role.md#one-class-key-in-every-role)), and no caller can rename it.
`class` is a Python keyword, so no struct confarg reads can own a member spelled like it, and the key never stands for a field:

```text
make_dataclass("D", ["class"])          -> TypeError: Field names must not be keywords: 'class'
namedtuple("N", ["class"])              -> ValueError: Type names and field names cannot be a keyword: 'class'
NamedTuple("N", [("class", int)])       -> ValueError: Type names and field names cannot be a keyword: 'class'
attrs.make_class("A", {"class": ...})   -> SyntaxError in the generated __init__
inspect.Parameter("class", ...)         -> ValueError: 'class' is not a valid parameter name   (a plain class is read by its signature)
```

A Protocol's members come from its class body, which cannot spell `class` either.
`type` was rejected as a common field name.
Cost: unusual for users expecting `type`, and reads slightly oddly in files.

The key is fixed like every other reserved word: `classfn`, `bind`, `call`, `args`, `__include__`, `__cast__`, `__value__`, `__root__`, the list ops' spellings and the locals namespace.
Since none can be renamed, none can collide with another, and nothing checks a spelling on entry.

Why: the key was once the `union_tag` option, configurable per call, from when it was confarg's only reserved key and selected a union's variant only.
Once it became the class opener of every spec, a custom spelling renamed one opener of four (`{kind: pkg.Mul}` beside `{classfn: pkg.Loss.from_name}`), cost a check keeping it off every key another role spells, and imported whatever a `type` entry under an `Any` named under `union_tag="type"`.
A field spelled like a custom key also needed its own family of rules: the real field won, a shadowed key warned on use, a subclass-only owner was read through its siblings, and `dump()` wrote no key over an owner (BUG-92, 97, 102, 103, 106, 276, 285, 302, 303).
Under `class` none of these can happen, so they went with the option (REF-121, maintainer-chosen).

Precedents: config languages fix their key.
Hydra and detectron2's LazyConfig use `_target_`, jsonargparse uses `class_path`, and the mmcv and AllenNLP registries use `type`; none of them can be renamed.
Serialization libraries make the tag configurable (serde's `#[serde(tag = …)]`, msgspec's `tag_field`, pydantic's `discriminator`), but per type, never per call.
There the tag is a data field that only selects among a union's members, and never opens a callable spec.
confarg's key opens a Callable's and an `Any`'s spec, which have no type to hang a per-type option on, so confarg belongs to the first family.

Rejected:

- **Keep the `union_tag` option for a foreign format whose discriminator is spelled otherwise.**
  An mmdet-style `{type: ResNet, depth: 50}` is no longer read as it stands; the caller renames the key before `build()` or `from_dict()`, as a Hydra user does to reach `_target_` ([limitations](../limitations.md#subclasses)).
- **Configure it per type**, as msgspec and serde do.
  It fits a union of structs, but not the opener of a lone `Callable` or `Any`, which has no class of its own to carry the option.
- **A process-wide setting.**
  It is global state: two libraries in one process configuring with confarg would disagree.
- **Keep the shadowed-key machinery dormant until FEAT-45.**
  Nothing reachable would exercise it, so its tests could only call internals.
  A TypedDict accepts a `class` key (`TypedDict("T", {"class": str})`), but is no struct yet: FEAT-45's design pass chooses between refusing that key, the way Hydra and jsonargparse reserve theirs everywhere, and bringing a real-field-wins rule back for it.
- **Keep "union tag" as the internal name.**
  Less churn, but two names for one key, and the internal name describes the narrowest of its roles.

A dict variant holding `class` as data where no class key selects (BUG-276) is not a member owning the key: it stays ([construction](../types/construction.md#where-no-tag-selects-a-variant-that-reads-a-dict-holds-the-key-as-data)).

An untyped merge (`MergeAt()`, the shape rule with no type to read) reads the class key too: a dict carrying it replaces what lies below, as the shape rule says of every node ([the type decides replace or refine](the-type-decides-replace-or-refine.md#the-type-decides-whether-a-value-replaces-or-refines)).
Under the option, the untyped merge read no key at all.
