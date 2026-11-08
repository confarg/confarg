---
filed: 2026-10-25
where:
  - src/confarg/_parse_cli.py::_restart_restated_node  # no-matching-overload on node.update(kept)
  - src/confarg/_typed_merge.py::TypedAt  # invalid-mutable-override of union_tag, as in _RootAt and _ArgsAt
  - src/confarg/_typed_merge.py::_RootAt
  - src/confarg/_typed_merge.py::_ArgsAt
  - tests/cli/test_backend_contract.py::_OverOverride  # its mypy-style `type: ignore[assignment]` no longer silences ty
  - tests/cli/test_backend_contract.py::_WidenSub
  - tests/cli/test_backend_contract.py  # test_every_spelling_builds_the_callable, two invalid-assignment
effort: S
risk: low  # annotations and suppressions; a real fix in _typed_merge or _parse_cli is covered by the suite
impact: none
severity: minor  # `uv run ty check` fails on a tree with no new type error, so a real one hides among nine
---

# REF-118 — The tree does not type-check under the locked ty

`uv run ty check` reports nine errors since `uv.lock` moved ty from 0.0.85 to 0.0.91, in the revision that closed BUG-195, BUG-252 and BUG-256; ty 0.0.85 passes the same tree (`uv run --with ty==0.0.85 ty check`).
The new rules flag a `MergeDict.update` overload in `_parse_cli._restart_restated_node`, the `union_tag: str` that `TypedAt`, `_RootAt` and `_ArgsAt` declare over `MergeAt`'s `str | None` (`invalid-mutable-override`), three test dataclasses that override a field with another type on purpose (`invalid-attribute-override`; `_OverOverride` carries a mypy-style `# type: ignore[assignment]` ty no longer reads as its own), and two subscript assignments into a `dict[str, Any & str]` in `test_every_spelling_builds_the_callable`.
Each is a real fix or a suppression naming its rule and its reason *(inferred: which of the nine are ty false positives on a pre-1.0 release is not checked)*.
Found running `ty check` after fixing BUG-278, on its parent revision as on it.
