---
filed: 2026-10-07
where:
  - src/confarg/_sources.py::_read_file_url
effort: S
risk: low
impact: none
severity: trivial  # a type-checker warning, no user meets it
---
# REF-88 — The `deprecated` suppressions in `_sources.py` warn as unused below Python 3.14

`_read_file_url` silences `ty`'s `deprecated` rule twice for `urllib.request.url2pathname`,
which is soft-deprecated only from Python 3.14. When `ty check` resolves an older
interpreter, as it does in the project's 3.12 environment, nothing is deprecated, so both
comments are reported as `unused-ignore-comment` warnings. The check is clean on 3.14 only,
while CI tests 3.12, 3.13 and 3.14. Fix direction: make the suppression hold on every
supported version, either by naming both rules on the line or by pinning the interpreter
version `ty` checks against in `pyproject.toml`.

Observed on the FEAT-30 revision and after it, with Python 3.12.11:

```console
$ uvx --with click --with argcomplete ty check
warning[unused-ignore-comment]: Unused `ty: ignore` directive
  --> src\confarg\_sources.py:58:63
warning[unused-ignore-comment]: Unused `ty: ignore` directive
  --> src\confarg\_sources.py:67:51
```
