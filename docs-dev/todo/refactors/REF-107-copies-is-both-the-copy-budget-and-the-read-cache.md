---
filed: 2026-10-20
where:
  - src/confarg/_depth.py::Copies
  - src/confarg/_files.py::_identity
  - src/confarg/_files.py::_joined
  - src/confarg/_files.py::_load_any
effort: S
risk: low
impact: none
severity: trivial
---

# REF-107 — `Copies` is both the copy budget and the read cache

BUG-259 gave one configuration one `_depth.Copies`, threaded through every walk that charges it, and made it the place a location is read once: besides `spent`, it holds `joined`, `identities`, `read` and `documents`, which `_files._joined`, `_files._identity` and `_files._load_any` fill.
The decision to read a location once is sound ([one budget per configuration](../../architecture/design-decisions/a-configuration-copies-at-most-100000-positions.md#one-budget-per-configuration)); housing it in a class named for the budget is not:

- a reader of `_files` meets `copies=copies` on calls that copy nothing and only read through the cache;
- `_files._identity` shadows the canonical `_sources._identity` ("are these two locations the same document?") under the same name, adding only the cache;
- `Copies.bound` is a property that returns the module constant `MAX_COPIED`, read only to be passed back into the refusal factories.

Fix direction: either rename the class for what it is — the state of reading one configuration (`Reading`, holding the budget and the caches) — or split the caches into a `_files`-owned object the same calls carry; drop `bound` for `MAX_COPIED`, and name the cached lookups `_cached_identity` / `_cached_join`.
