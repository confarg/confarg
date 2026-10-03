# BUG-90 — The env channel drops a root-level CLASS variable on a struct-walked root

**Where:** `src/confarg/_parse_env.py` (`_warn_unknown_env_field`, and the walk that calls it) ·
**Filed:** 2026-09-30
**Effort:** S · **Risk:** medium · **Impact:** behavior

The CLI and file channels accept a class tag at the root of any struct-walked target —
vanilla's type walk answers the tag segment through the `union_tag` rule whatever the
target, and a config file's top-level `class:` key reaches `build()` untouched. The env
channel's first-segment check never consults the tag: `_warn_unknown_env_field` asks only
`parts[0] not in _struct_fields(root_tp)`, and the union tag is not a field, so
`PFX_CLASS` is warned away and ignored — even when it names a real subclass of the root,
which the CLI channel of the same configuration accepts. Bites a root target that is a
registered leaf (whose only flat hatch spelling on the CLI is the tag,
[an-explicit-tag-opts-a-leaf-back-in.md](../../architecture/design-decisions/an-explicit-tag-opts-a-leaf-back-in.md#an-explicit-tag-opts-a-leaf-back-in))
and an inheritance-dispatch root alike. Found while closing BUG-71, whose fix made the
CLI channel accept what the env channel still refuses.

```python
from uuid import UUID
import confarg

confarg.register_leaf_type(UUID, UUID)
hx = "12345678123456781234567812345678"

cli = confarg.merge(UUID, argv=["--v.class", "uuid.UUID", "--v.hex", hx], cli_prefix="v")
env = confarg.merge(UUID, env={"MYAPP_CLASS": "uuid.UUID", "MYAPP_HEX": hx}, env_prefix="MYAPP_")
print(cli)
print(env)
# expected: both print {'class': 'uuid.UUID', 'hex': '12345678123456781234567812345678'}
# actual:
#   cli: {'class': 'uuid.UUID', 'hex': '12345678123456781234567812345678'}
#   env: ConfargWarning: Environment variable 'MYAPP_CLASS' has no matching field
#        (segment 'class' not found in UUID). Known fields: ['bytes', 'bytes_le',
#        'fields', 'hex', 'int', 'is_safe', 'version']. The variable will be ignored.
#        {'hex': '12345678123456781234567812345678'}
```
