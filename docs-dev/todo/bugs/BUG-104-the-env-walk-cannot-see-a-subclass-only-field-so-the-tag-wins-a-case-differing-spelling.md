# BUG-104 — The env walk cannot see a subclass-only field, so the tag wins a case-differing spelling

**Where:** `src/confarg/_parse_env.py` (`_match_env_part`, via `_match_struct_part`) · **Filed:** 2026-10-01
**Effort:** S · **Risk:** medium · **Impact:** config

The resolution walk answers "a member case-insensitively, then the union tag by its own
spelling" ([invariants](../../architecture/invariants.md)), and a subclass-only field is a
member ([real-field-wins](../../architecture/cli-parsing/casts-and-reserved-words.md#real-field-wins),
BUG-103). But `_match_struct_part` asks the base's own `_struct_fields` only, so a
subclass-only field never matches and the tag fallback takes the spelling. This bites when a
subclass-only field differs from the tag by case alone: the CLI channel keeps the two
distinct (`--kind` the field, `--Kind` the tag, exact matching), so the same intended
setting merges under different keys per channel — and the env route's key is the tag, so
`build()` imports the field's value as a class path. The unknown-field warning already counts
subclass-only fields as members (`_segment_names_real_field`, BUG-90); only the walk lags.
Fix direction: the struct branch of the walk should match subclass-only fields too, by the
canonical `_subclass_field_type`, keeping the member-first order.

```python
from dataclasses import dataclass

import confarg


@dataclass
class Base:
    pass


@dataclass
class Sub(Base):
    kind: str = "f"


print(confarg.merge(Base, argv=["--kind", "v"], env={}, union_tag="Kind"))
# expected: {'kind': 'v'} — the member wins the case-insensitive race, as on the CLI channel
print(confarg.merge(Base, argv=[], env={"APP_KIND": "v"}, env_prefix="APP_", union_tag="Kind"))
# actual:   {'Kind': 'v'} — the tag, so build() tries to import 'v' as a class path
```
