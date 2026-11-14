---
filed: 2026-11-09
where:
  - pyproject.toml  # pins pytest-markdown-console, whose runner.py calls subprocess.run(..., text=True)
effort: S
risk: low
impact: none
severity: trivial  # only the test run on Windows meets it, and PYTHONUTF8=1 is a workaround
introduced_by: [PR-35]  # the earliest revision found naming the plugin
---

# BUG-320 — Console examples fail on Windows, decoding their output as the locale

Five console blocks fail in a full test run on Windows: `examples/12_collections/README.md` block 22, `examples/3_scalar_types/README.md` blocks 35 and 36, and `examples/5_generics/README.md` blocks 3 and 4.
`pytest_markdown_console/runner.py` runs each command with `subprocess.run(..., capture_output=True, text=True)` and no encoding, so Windows decodes its output as cp1252.
The cyclopts and typer error boxes are UTF-8, and `┐` holds the byte `0x90`, which cp1252 does not map: the reader thread dies, `result.stderr` is `None`, and the runner's `.rstrip` raises `AttributeError`.
CI runs on Ubuntu and does not meet it (*inferred*: not run on Linux here).

Fix direction: pass `encoding="utf-8"` in the plugin's runner and bump the pin; failing that, set `PYTHONUTF8=1` for the test run.
With `PYTHONUTF8=1` the five blocks pass (run).

Origin: latent since the plugin was adopted; the earliest revision found naming it is PR-35, and the `text=True` is in the plugin's own runner.

```python
import subprocess
import sys

CHILD = "import sys; sys.stderr.buffer.write('\\u2510'.encode('utf-8'))"
result = subprocess.run([sys.executable, "-c", CHILD], capture_output=True, text=True, check=False)
print(repr(result.stderr))
# expected: '┐'
# actual, on Windows under cp1252:
#           UnicodeDecodeError: 'charmap' codec can't decode byte 0x90 in position 2: character maps to <undefined>
#           None
```
