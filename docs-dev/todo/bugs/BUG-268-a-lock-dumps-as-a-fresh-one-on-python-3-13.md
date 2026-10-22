---
filed: 2026-10-22
where:
  - src/confarg/_serialize.py::_held_object_form
  - src/confarg/_serialize.py::_reads_back
  - src/confarg/_types.py::_is_plain_class
  - tests/test_config_files.py::TestAFileRefusesAValueItsFormatDoesNotHold
effort: M  # the design pass: whether a class taking nothing but holding hidden state is a struct
risk: medium
impact: behavior
severity: minor  # close to critical: the dump silently loses a lock's state, but no configuration is misread
needs_design: true
introduced_by: [FEAT-14]  # met by Python 3.13, where threading.Lock became an importable class
---

# BUG-268 — On Python 3.13+, a lock dumps as a fresh one, with no warning

`threading.Lock` is the importable class `_thread.lock` since Python 3.13; on 3.12 it was a factory function returning an instance of a class no dotted path names.
`_thread.lock` takes nothing, so it reads as a struct with no fields ([a class taking nothing is a struct with no fields](../../architecture/design-decisions/a-structs-members-are-its-constructors-parameters.md#a-class-taking-nothing-is-a-struct-with-no-fields)), and its path now imports back, so an `Any` field holding a lock dumps as `{class: _thread.lock}`.
`_reads_back` accepts that spec: the lock it rebuilds compares unequal but dumps back as the same spec, the "same state" test of [an Any node dumps the spec that rebuilds it](../../architecture/types/serialization.md#an-any-node-dumps-the-spec-that-rebuilds-it), so no warning is raised and `dump_file()` writes the spec, which reloads as a fresh, unlocked lock.
The state a C object holds out of reach (a lock's locked flag) is compared by nothing, so the dump is lossy and says nothing.

The six tests of `TestAFileRefusesAValueItsFormatDoesNotHold` that use a lock assume 3.12 and fail on 3.13 and 3.14, which CI runs: `dump_file()` no longer refuses it.

Fix direction, for the design pass: whether a class whose signature takes nothing and whose instances hold no `__dict__` or slot state is a struct at all, or whether the "same state" test should refuse to call two objects the same when nothing observable was compared.
The tests then need an object no path names on any version, or a lock refused for the reason chosen.

Origin: latent since FEAT-14/BUG-153 made a class taking nothing a struct with no fields, which met Python 3.13's `threading.Lock` change; the tests BUG-251 added have failed on 3.13+ since they were written (run at that revision on 3.14: 6 failed).

```python
@dataclass
class LockHolder:
    lock: Any = field(default_factory=threading.Lock)


confarg.dump(LockHolder())
# expected (3.12): {'lock': <_thread.lock object>} with a ConfargWarning, and dump_file() refuses it
# actual (3.13, 3.14): {'lock': {'class': '_thread.lock'}}, no warning; dump_file() writes it
```
