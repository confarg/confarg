# BUG-50 — A `--config.<subpath>` naming no field mounts silently, and dict fields get no flag

**Where:** `src/confarg/_parse_cli.py` (`_config_subpath`, `_consume_config_paths`),
`src/confarg/_parse_env.py` (`_handle_env_config_flag`), `src/confarg/cli/_build.py`
(`_collect_subconfig_specs`) · **Filed:** 2026-09-26
**Effort:** M · **Risk:** medium · **Impact:** behavior

Two halves of one gap: the mount subpath is never checked against the target type, and the
`--help` entries that would have shown the valid ones are only generated for struct fields.

`_config_subpath` slices the flag name and hands the result to the pipeline, which nests the
loaded fragment under it whatever it names; `_handle_env_config_flag` lowercases its segments
against the type tree but does not reject one that matches nothing either. So `--config.dbb`
mounts a whole file at a key nobody declared, and the mistake surfaces much later as an
unknown-field error from `build()` naming `dbb` rather than as "no such field to mount at".
Every other dotted CLI path is resolved against the type as it is parsed
([03-cli-parsing.md#type-guided-parsing](../../architecture/03-cli-parsing.md#type-guided-parsing));
this one is the exception, and the reason it is the exception is that the config flag is
intercepted *before* field lookup
([10-design-decisions.md#the-mount-keyword-is-spelled-per-channel](../../architecture/10-design-decisions.md#the-mount-keyword-is-spelled-per-channel)).
A check after interception costs one `_resolve_field_type` call.

Meanwhile `_collect_subconfig_specs` skips any field that is not a struct
(`if not _is_struct(core): continue`), so `--config.plugins` never appears in `--help` for a
`dict[str, str]` field even though mounting a fragment there works — and a dict node is one of
the places the feature is most useful, since it is exactly where a fragment of unknown keys
belongs. Fixing the two together is what makes the flag discoverable *and* checkable: the same
type walk answers "is this a real mount point?" for both.

```python
from dataclasses import dataclass, field
import pathlib, tempfile
import confarg
from confarg.cli import build_static_flags

d = pathlib.Path(tempfile.mkdtemp())
(d / "db.yaml").write_text("host: filehost\nport: 1\n")


@dataclass
class Db:
    host: str = "h"
    port: int = 0


@dataclass
class C:
    db: Db = field(default_factory=Db)
    plugins: dict[str, str] = field(default_factory=dict)


print(confarg.merge(C, argv=["--config.dbb", str(d / "db.yaml")], env={}))
print(sorted(f.name for f in build_static_flags(C, union_tag="class", config_flag="config")
             if f.name.startswith("config")))

# expected: a ConfargError naming 'dbb' as no field of C to mount at, and a registered
#           'config.plugins' alongside 'config.db'
#   ConfargError: --config.dbb names no field of C. ...
#   ['config', 'config._locals', 'config.db', 'config.locals', 'config.plugins']
# actual:   the file is mounted at an invented key, and the dict field has no flag
#   {'dbb': {'host': 'filehost', 'port': 1}}
#   ['config', 'config._locals', 'config.db', 'config.locals']
```

The same `--config.dbb` through `confarg.load` reaches
`TypeCoercionError: Unknown field(s) ['dbb'] for C at ''. Valid fields: ['db', 'plugins']`, and
`MYAPP_CONFIG__DBB` reaches the identical error, so neither channel is better off.
