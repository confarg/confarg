---
filed: 2026-10-19
where:
  - tests/test_cli.py::TestUnionTagFieldCollision
  - tests/test_env.py::TestEnvSubclassOnlyTagCollision
  - tests/cli/test_backend_contract.py::TestUnionTagFieldCollision
  - tests/typedload/test_construct.py::TestTagFieldCollision
  - pyproject.toml  # [tool.pytest.ini_options], which sets no filterwarnings
effort: S
risk: low
impact: none
severity: trivial
---

# REF-95 — The tag-collision tests leave their warnings uncaptured

Every full run prints 34 `ConfargWarning`s, "The 'Kind' key at '__root__' is a field's value, not the tag: a member owns the tag's spelling there …", from the tests of a field named like the union tag.
The warning is the documented behavior ([real field wins](../../architecture/design-decisions/real-field-wins.md)), but these tests assert the build alone, so the warning reaches the summary instead of being checked: nothing fails if it stops being raised, or if a test elsewhere starts raising one by accident.
Wrapping each in `pytest.warns(ConfargWarning, match=…)` checks it; `filterwarnings = ["error::confarg.exceptions.ConfargWarning"]` would then keep any other test from leaking one.
Found while fixing BUG-248; the parent revision prints the same 34.

`-W error::confarg.exceptions.ConfargWarning` over the four files fails exactly these 33 test cases (the 34th warning is a second one in a test already listed): `TestUnionTagFieldCollision` in `tests/test_cli.py` (5) and in `tests/cli/test_backend_contract.py` (3 tests × 5 front-ends), `TestEnvSubclassOnlyTagCollision` (1 × 5) and `TestTagFieldCollision` (8).
