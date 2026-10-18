---
filed: 2026-10-18
where:
  - src/confarg/_api.py::dump
  - src/confarg/_api.py::dump_file
effort: M
risk: low
impact: behavior
severity: minor  # refused with a TypeError; dumping the merged dict, which holds __root__, works
---

# FEAT-55 — Dumping a configuration whose root is no struct

`load()` builds a target that is no struct, a `list[int]`, a `dict[str, int]` or an `int`, from the `__root__` key of a root file ([reserved keys](../../architecture/config-files/reserved-keys.md#reserved-file-only-keys)).
`dump()` and `dump_file()` refuse the value it builds: `confarg.dump([1, 2])` raises `TypeError: Expected a dataclass or plain-class instance, got list`, and `dump_file()` reads a built `dict` as a merged dict, writing it without the `__root__` key `load()` reads.
The merged dict holds `__root__` already (`merge(list[int], ...)` is `{'__root__': [1, 2]}`), so `dump_file(merge(...))` is the way around it today.
Direction: take the root type, `dump(value, tp=list[int])` or a target argument, serialize the value as that type, and write it under `__root__`, so that it loads back.
A dumped file reloads only once [BUG-242](../bugs/BUG-242-a-lone-root-key-in-a-root-file-is-unwrapped-as-a-fragments.md) stops unwrapping a lone `__root__` at a document root.
