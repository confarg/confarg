---
filed: 2026-10-06
where:
  - src/confarg/_parse_cli.py::_strip_cli_prefix
  - src/confarg/exceptions.py::UnknownArgumentError
effort: S
risk: low
impact: behavior
severity: minor
introduced_by: [PR-5]  # the prefix check runs on the raw flag name, merge suffix included
---

# BUG-178 — A bare-prefix append is told it lacks the prefix

`--<prefix>+` is checked against the namespace before its merge suffix is read, so `_in_cli_prefix` sees `app+`, which is neither `app` nor below `app.`, and the flag is refused with the message for a flag outside the prefix.
That message is false about the token it quotes.
The refusal itself stands: no flag appends onto the root, whose value is set whole ([cli_prefix](../../architecture/cli-parsing/cli-prefix.md#a-non-struct-root-is-set-whole)).
The fix direction is to recognise the suffix before the namespace check, the way `_addresses_key` already reads the config flag's `+`, and to refuse it as an append onto the root.

Origin: latent since the initial version (PR-5): the namespace check has always run on the flag name before its merge suffix is read.
It reproduces unchanged at PR-28.

```python
import confarg

try:
    confarg.merge(list[int], argv=["--app+", "1"], env={}, cli_prefix="app")
except Exception as e:
    print(type(e).__name__, e)

# expected: an UnknownArgumentError that says the root takes no append
# actual:   UnknownArgumentError Unknown argument: '--app+'. Expected arguments to start with --app.
```
