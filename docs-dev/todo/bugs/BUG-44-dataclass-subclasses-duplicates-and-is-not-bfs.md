# BUG-44 — `_dataclass_subclasses` returns a diamond subclass twice, and is not BFS

**Where:** `src/confarg/_types.py` (`_dataclass_subclasses`) · **Filed:** 2026-09-24
**Effort:** S · **Risk:** medium · **Impact:** behavior

Two defects in nine lines, both of which the standard library fixes:

- **Duplicates.** A class reachable by two inheritance paths is enqueued once per path and
  appended once per path. This is user-visible: `cli/_build.py:878-882` maps the result to
  `paths = [f"{v.__module__}.{v.__qualname__}" for v in all_subs]` and hands it to the union-tag
  selector, so a diamond subclass is offered **twice** in tab completion.
  `dict.fromkeys(found)` dedupes while preserving order.
- **The docstring is wrong about the code.** It promises "BFS order", but `queue.pop()` takes
  from the end of a list, so the walk is depth-first. `collections.deque` plus `popleft()` makes
  the code do what the docstring says.

The other caller, `_parse_cli.py:81` (`_subclass_field_type`), is unaffected either way — a
duplicate only adds an equal entry to a list it reduces with `all(f == first for f in ...)`.

Which half to change is a decision, not an edit: deduping is unambiguously right, but switching
DFS to BFS reorders completion output, so the alternative is to correct the docstring to say
depth-first and leave the traversal alone. Settle that before writing the fix, and record it
in [05-types-and-construction.md](../../architecture/05-types-and-construction.md) if the
ordering turns out to be load-bearing.

Risk is **medium**: nothing today asserts the order or the absence of duplicates, so a mistake
stays silent in the completion path while every other channel stays correct. Closing this means
adding a test there.

```python
from dataclasses import dataclass
from confarg._types import _dataclass_subclasses

@dataclass
class Base: x: int = 0
@dataclass
class A(Base): a: int = 1
@dataclass
class B(Base): b: int = 2
@dataclass
class C(A, B): c: int = 3

print([s.__name__ for s in _dataclass_subclasses(Base)])
# expected: each subclass once, breadth-first -> ['A', 'B', 'C']
# actual:   ['B', 'C', 'A', 'C']
```
