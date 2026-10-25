---
filed: 2026-10-25
where:
  - src/confarg/_tags.py::_argv_tag_names_member  # skips only a path whose type owns the tag's spelling
  - src/confarg/_tags.py::collect_tags
effort: M  # needs one answer per kind, beside typedload._construct.tag_reading, to "does a tag here select a class?"
risk: medium  # the argv channel only; importing too little drops a named subclass's flags from registration, silently
impact: behavior
severity: minor  # the value built is right; only the import's side effect is wrong
introduced_by: [BUG-6]  # PR-150: _tags_from_argv collects every --<path>.<union_tag> VALUE lexically
---

# BUG-286 — A `class` flag on a type no tag selects imports its value from argv

`--labels.class pkg.mod.Thing` on a lone `labels: dict[str, str]` imports `pkg.mod`, running its top level, though the value is a dict entry construction holds as data; the same entry in a file imports nothing.
The same holds for a plain leaf, `--x.class pkg.mod.Thing` on `x: int`, which construction refuses before importing ([a tag no variant takes](../../architecture/types/construction.md#a-tag-no-variant-takes)).
The argv scan is lexical, and `_argv_tag_names_member` asks only whether the type at the path owns the tag's spelling (`_union_tag_shadowed`); `_tags_from_config` walks the type and collects a tag only on a struct or a union field, so the two channels disagree.
A union is already right: since BUG-276 both ask `typedload._construct.tag_reading` and import only a tag that selects a variant.
Fix direction: let the argv scan import a tag only where the type at its path reads it as selecting a class, which is a struct or a registered leaf whose member does not own the spelling, a union `tag_reading` answers `SELECTS` for, or a Callable or an `Any` reading a spec; the import before registration exists for those alone ([a named tag is imported before registration](../../architecture/design-decisions/a-named-tag-is-imported-before-registration.md#a-named-tag-is-imported-before-registration)).
A path the walk cannot resolve keeps importing, as today.

Origin: latent since BUG-6 (PR-150), which imported a named class tag before registering flags, so that a subclass nobody imported got its flags; it scanned argv for every `--<path>.<union_tag> VALUE` without asking the type at the path.
BUG-102 (PR-262) added `_argv_tag_names_member` so a real field owning the spelling is never imported, and covered that case only.

`noisy.py`, beside the script:

```python
print("noisy imported")


class Thing:
    pass
```

`repro.py`:

```python
from dataclasses import dataclass, field

import confarg


@dataclass
class Cfg:
    labels: dict[str, str] = field(default_factory=dict)


print(confarg.load(Cfg, argv=["--labels.class", "noisy.Thing"], env={}).labels)
# expected: {'class': 'noisy.Thing'}
# actual:   noisy imported
#           {'class': 'noisy.Thing'}
```
