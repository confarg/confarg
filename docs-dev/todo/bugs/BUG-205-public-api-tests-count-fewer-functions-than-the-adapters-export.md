---
filed: 2026-10-07
where:
  - tests/cli/click/test_click_integration.py::test_public_api  # the docstring and the assertions
  - tests/cli/cyclopts/test_cyclopts_integration.py::test_public_api  # the docstring and the assertions
effort: S
risk: low
impact: none
severity: trivial
introduced_by: [PR-63]  # wrote both pins six days after PR-60 grew __all__ with merge_context / merge_app
---
# BUG-205 — The click and cyclopts public-API tests count fewer functions than the adapters export

`test_public_api` says "the four documented public functions" while `confarg.cli.click`'s `__all__` holds five, and "the three documented" while `confarg.cli.cyclopts`'s holds four. Neither asserts the `merge_*` entry point PR-60 exposed, so a rename or removal of `merge_context` / `merge_app` — the adapters' merge seam, which [pipeline/api-seams.md#public-api-seams](../../architecture/pipeline/api-seams.md#public-api-seams) counts among the public API — passes the pin unnoticed. Fix direction: assert every name in `__all__`, so the count cannot drift again. The typer and argparse adapters carry no such test at all.

Origin: latent from PR-63 ("fix: Remove implicit subclass discovery"), which wrote both pins against the export list as it stood before PR-60 ("Expose unresolved dicts in CLI integration") — but PR-60 had grown `__all__` with `merge_context` / `merge_app` six days earlier, so the counts and the assertions were short from birth.

```console
$ grep -A6 "__all__ = \[" src/confarg/cli/click/__init__.py
__all__ = [
    "from_context",
    "load_flags_into_command",
    "merge_context",
    "populate_command",
    "setup_completion",
]
$ grep -A5 "__all__ = \[" src/confarg/cli/cyclopts/__init__.py
__all__ = [
    "from_app",
    "load_flags_into_app",
    "merge_app",
    "populate_app",
]
$ grep -n "documented public functions" tests/cli/click/test_click_integration.py tests/cli/cyclopts/test_cyclopts_integration.py
tests/cli/click/test_click_integration.py:362:    """confarg.click exports the four documented public functions."""
tests/cli/cyclopts/test_cyclopts_integration.py:383:    """confarg.cli.cyclopts exports the three documented public functions."""
# expected: five and four, the sizes of the two __all__ lists
# actual:   four and three, and neither test asserts merge_context / merge_app
```
