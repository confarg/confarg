---
filed: 2026-10-25
where:
  - src/confarg/typedload/_construct.py::_warn_shadowed_tag_key  # _spell_field_path(path) or _defaults.ROOT_KEY
  - src/confarg/exceptions.py::tag_shadowed_by_member  # ConfargWarning's, "the root spelled as its own key"
effort: S
risk: medium  # nothing pins the warning's text (REF-95); a wrong spelling shows in every channel, in a warning only
impact: behavior
severity: minor  # a misleading message; the build is right
introduced_by: [PR-264]  # added the warning, spelling the empty path as _defaults.ROOT_KEY
---

# BUG-285 — A shadowed-tag warning at a struct root names the key `__root__`

When a member of a struct root, or of a root union of structs, owns the union tag's spelling, the warning says the key is "at '__root__'", a key the user never wrote: the value sits at the top of the configuration, `--Kind v` or a file's `Kind: v`, and only a root set whole is held under `__root__`.
The same warning one level down names the field, "at 'pet'", so only the root is misnamed.
Fix direction: spell the empty path as "the root", as `TypeCoercionError.keys_beside_a_whole_root` and the appended-document messages already do, and drop "the root spelled as its own key" from `tag_shadowed_by_member`'s contract; [real field wins](../../architecture/design-decisions/real-field-wins.md) is the rule the warning reports.
REF-95, which wraps the tag-collision tests in `pytest.warns`, is the place to pin the new text.

Origin: latent since PR-264, which added the warning to name a structural selection where a class-path tag could have dispatched, and spelled the empty path as `__root__` on purpose, reading the root as the key a non-struct root is held under; at a struct root no such key exists.
BUG-169 (PR-335) carried the spelling over when the path became segments, unchanged.

```python
import warnings
from dataclasses import dataclass

import confarg


@dataclass
class A:
    Kind: str = ""


@dataclass
class B:
    z: int = 0


with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    confarg.load(A | B, argv=["--Kind", "v"], env={}, union_tag="Kind")
print(str(caught[0].message))
# expected: The 'Kind' key at the root is a field's value, not the tag: a member owns the tag's spelling there, ...
# actual:   The 'Kind' key at '__root__' is a field's value, not the tag: a member owns the tag's spelling there, so no class-path tag can dispatch and the variant is selected structurally. Rename the field or pass a different union_tag to keep the tag's spelling available.
```
