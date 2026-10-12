---
filed: 2026-10-12
where:
  - src/confarg/_merge.py::_starts_afresh
  - src/confarg/_merge.py::_deep_merge
  - src/confarg/_merge.py::_is_call_dict
  - src/confarg/_merge.py::_merge_existing_value
effort: L
risk: high
impact: behavior
severity: critical  # lower layers' keys vanish and the object builds without them, no error
needs_design: true  # the merge decides by key alone, construction by type; one of the two has to move
introduced_by: [PR-5, BUG-102, BUG-23]  # PR-5: dict/Any keys and the layered shorthand; BUG-102: a struct owning the tag's spelling; BUG-23: the shorthand refined in one source only
---
# BUG-232 — The merge decides by shape what only the type can tell

Between layers, `_deep_merge` decides by a value's shape alone whether a higher layer replaces what lies below or refines it. Two of those decisions need the type, which construction and the CLI and environment parsers have and the merge does not, so the same input means one thing within one source and another across layers.

**A union tag the type holds as data replaces what lower layers set.** A dict holding the tag is a new object to the merge (`_starts_afresh`), which drops the lower layers' keys at its node. Construction decides by type: a struct that owns a field spelled like the tag keeps it as that field (`_union_tag_shadowed`, [real field wins](../../architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins)), and a `dict` or `Any` field holds any key as data. There, a higher layer writing the key as data silently erases the lower layers' other keys: a struct field falls back to its default, a dict loses its entries, from a file, `--labels.class confidential` or the environment alike. Replacing is right where the key is the tag ([a class tag replaces](../../architecture/design-decisions/class-tag-replaces.md)). A `call:` replaces by the same rule and has the same cost where the type holds `call` as data ([a call replaces what lies below](../../architecture/design-decisions/a-call-replaces-what-lies-below.md#a-call-replaces-what-lies-below)).

**A lower layer's callable shorthand is replaced by the higher layer that refines it.** `fn: pkg.shout` is `{bind: pkg.shout}` on a Callable field, so `--fn pkg.shout --fn.args.punct !` refines the target, opened by the CLI and environment parsers, which know the field's type (`_open_callable_shorthand`, [whole value then subkey](../../architecture/design-decisions/whole-value-then-subkey.md)). Across layers, `_merge_existing_value` lets the higher dict replace the lower string, the target is lost, and construction refuses a spec with no opener.

A fix should settle both, and `bind` and `classfn` over another opener ([BUG-231](BUG-231-a-callable-opener-merges-with-the-spec-a-lower-layer-set.md)), through one type-aware decision of whether a value replaces or refines what lies below. [BUG-107](BUG-107-a-nested-real-field-named-like-the-tag-is-stripped-by-the-union-type-check.md) is the same family: another reader that takes a tag-spelled key for the tag where a real field owns it.

Origin: three revisions. The initial version (PR-5) already replaced on `union_tag in override` while construction kept a `dict` field's keys as data, and already let a higher dict replace a lower callable string: the dict, `Any` and layered-shorthand cases are latent since then (the first two reproduce unchanged at PR-5; the third loses the target there too, with another symptom). BUG-102's fix let a real field win the tag's exact spelling in construction and left the merge reading the key as the tag: before it, `{kind: stream}` over `{kind: batch, retries: 3}` failed loudly as a tag naming no class; at it, it builds `Job(kind='stream', retries=0)`. BUG-23's fix taught the CLI and environment to open the shorthand a later key refines, within one source, and its decision left the layered case to a type-unaware merge. Two bug fixes, then, that each moved one half of a shared decision and not the other.

```python
import pathlib
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import confarg


def shout(name: str, punct: str = ".") -> str:
    return name.upper() + punct


@dataclass
class Job:
    kind: str = "batch"
    retries: int = 0


@dataclass
class Config:
    job: Job = field(default_factory=Job)
    labels: dict[str, str] = field(default_factory=dict)
    extra: Any = None
    fn: Callable[[str], str] = shout


d = pathlib.Path(tempfile.mkdtemp())


def load(lower: str, upper: str, argv: list[str] | None = None, **opts: Any) -> Config:
    (d / "a.yaml").write_text(lower)
    (d / "b.yaml").write_text(upper)
    return confarg.load(Config, argv=argv or [], env={}, files=[d / "a.yaml", d / "b.yaml"], **opts)


print(load("job: {kind: batch, retries: 3}\n", "job: {kind: stream}\n", union_tag="kind").job)
# expected: Job(kind='stream', retries=3)
print(load("labels: {team: ml, tier: gold}\n", "labels: {class: confidential}\n").labels)
# expected: {'team': 'ml', 'tier': 'gold', 'class': 'confidential'}
print(load("labels: {team: ml, tier: gold}\n", "{}\n", argv=["--labels.class", "confidential"]).labels)
# expected: {'team': 'ml', 'tier': 'gold', 'class': 'confidential'}
print(load("extra: {a: 1, b: 2}\n", "extra: {class: x}\n").extra)
# expected: {'a': 1, 'b': 2, 'class': 'x'}
try:
    print(load(f"fn: {__name__}.shout\n", "{}\n", argv=["--fn.args.punct", "!"]).fn("hi"))
except confarg.exceptions.ConfargError as e:
    print(f"{type(e).__name__}: {e}")
# expected: HI!
```

Actual output, from the revision that filed this:

```text
Job(kind='stream', retries=0)
{'class': 'confidential'}
{'class': 'confidential'}
{'class': 'x'}
TypeCoercionError: Callable dict at 'fn' must specify one of 'bind', 'class', 'call' or 'classfn'
```
