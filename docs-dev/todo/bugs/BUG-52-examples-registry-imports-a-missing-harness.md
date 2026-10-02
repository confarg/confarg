# BUG-52 — `tests/examples/_registry.py` imports a harness that is not in the tree

**Where:** `tests/examples/_registry.py` · **Filed:** 2026-09-28
**Effort:** S · **Risk:** low · **Impact:** none

`_setup_custom_leaf_type` imports `load_script_module` from `.test_readme_commands`, and that
module does not exist: `tests/examples/` holds only `__init__.py` and `_registry.py`. Nothing
imports `_registry` either, so it is dead weight — but the dangling import makes `ty check`
report a diagnostic on a clean tree, and a clean tree is required to type-check clean, so the one
standing diagnostic is noise every contributor has to learn to ignore.

The module's docstring describes an in-process replay of every README `uv run` command through
all five front-ends. No such harness is in the tree, and
[12-testing.md#examples-and-documentation](../../architecture/12-testing.md#examples-and-documentation)
describes the example suite as subprocess-only, via `pytest-markdown-console`. So either the
replay harness comes back or the registry goes; whichever, `tests/examples/` should stop pointing
at a module that is not there. Deleting it is the smaller change, and no test references it.

<!-- pytest-markdown-console: notest -->
```console
$ ls tests/examples/
__init__.py
_registry.py

$ grep -rn "from .test_readme_commands" tests/examples/_registry.py
49:    from .test_readme_commands import load_script_module  # noqa: PLC0415  # circular at module level

$ uvx --with click --with argcomplete ty check
error[unresolved-import]: Cannot resolve imported module `.test_readme_commands`
  --> tests\examples\_registry.py:49:11
Found 1 diagnostic
```

expected: `ty check` reports no diagnostic on an unmodified tree.
actual: the one diagnostic above, on every run.
