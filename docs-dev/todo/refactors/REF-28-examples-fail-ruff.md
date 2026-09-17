# REF-28 — Three example scripts fail `ruff` on a clean tree

**Where:** `examples/100_completion/myapp2.py`, `examples/90_integration/myapp_module.py`,
`examples/90_integration/simple_inheritance.py` · **Filed:** 2026-09-17
**Effort:** S · **Risk:** low · **Impact:** none

`uv run pre-commit run --all-files` reports three errors with nothing modified, so the hook that
is supposed to gate every change starts out red and any real finding has to be read out of a
failing run. `examples/**` only silences the `D1xx` docstring rules in
[`.ruff.toml`](../../../.ruff.toml), so `ANN201` (two `def main():` without `-> None`) and
`PLC0415` (a function-level `import confarg.cli.argparse`) apply there like anywhere else.

Fix direction: annotate the two `main()` functions and lift the import — the import is inside
the function for no reason the example explains; if it has one, it is an inline
`# noqa: PLC0415` carrying that reason, not a new per-file ignore.
