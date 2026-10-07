---
filed: 2026-10-07
where:
  - src/confarg/typedload/_coerce.py::_LEAF_SERIALIZERS  # Path: str
---
# Q-5 — Should a `Path` dump with POSIX separators?

`Path` is registered with `str` as its serializer
([registered leaf serializer](../../architecture/design-decisions/registered-leaf-serializer.md)),
so a dump written on Windows spells `Path("logs/app.txt")` as `logs\app.txt`. Read back on
Windows, that is the same path. Read on a POSIX system, it is one file name with a backslash
in it: `PurePosixPath("logs\\app.txt").parts == ('logs\\app.txt',)`. Observed on Windows:

```python
confarg.dump(Config(p=Path("logs/app.txt")))  # {'p': 'logs\\app.txt'}
```

The options:

- keep `str`, the platform's own spelling. A dump stays a faithful record of the machine that
  wrote it, and a Windows-only path such as `C:\Users\x` reads back unchanged. pydantic's JSON
  mode writes a `Path` this way.
- write `as_posix()`. Windows reads forward slashes too, so a relative path dumped anywhere reads
  back everywhere. An absolute Windows path still names a drive, `C:/Users/x`, which no POSIX
  system resolves, so only relative paths gain.

A user can already choose by registering `Path` with a serializer of their own. The question is
which default the library ships.
