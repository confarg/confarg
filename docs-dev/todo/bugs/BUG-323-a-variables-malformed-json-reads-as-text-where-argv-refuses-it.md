---
filed: 2026-11-11
where:
  - src/confarg/_parse_env.py::_store_env_value  # suppresses JSONDecodeError and coerces the raw text
  - src/confarg/_parse_cli.py::_parse_json_arg  # argv's whole value, which refuses it
effort: M  # which variables still read a `{`/`[`-led value as text, and the message for each
risk: medium  # every whole-value variable whose type takes an object or a list
impact: config  # a variable read as text today is refused
severity: critical  # a str | dict field silently holds the malformed text, where argv refuses it
introduced_by: [PR-5]  # the initial version's env parser fell back to the token, its CLI raised
---

# BUG-323 — A variable's malformed JSON reads as text where argv refuses it

A `{`-led value at a field that takes an object is decoded as JSON on both channels ([environment parsing](../../architecture/environment-parsing.md#environment-parsing)), but only argv refuses one that is no JSON: `--u '{"x": 1,'` is `Invalid JSON for --u`, while `APP_U='{"x": 1,'` builds `u='{"x": 1,'` at a `str | dict[str, int]` field, with no error.
At a `dict[str, int]` field the variable fails, but as a coercion of text (`expected dict, got str`), which hides that the value was meant as JSON.
`_store_env_value` suppresses the `JSONDecodeError` and coerces the raw text; argv's whole value goes through `_parse_json_arg`, which raises.
The note promises a hard error on invalid JSON only for `<PREFIX>…__json`, so the difference is documented nowhere.

Fix direction: one decision-maker for a `{`/`[`-led whole value that is no JSON, read by both channels, refusing it naming the variable as argv names the flag.
A key written twice in such a value is already refused on both (BUG-313), being no `JSONDecodeError`.

Origin: latent since PR-5, the initial version, whose env parser wrapped `json.loads` in `except json.JSONDecodeError: pass` and fell through to `_try_coerce`, while its CLI's `_parse_json_arg` raised `Invalid JSON for {flag}`; REF-53 later spelled the env's as `contextlib.suppress`.

```python
from dataclasses import dataclass, field

import confarg
from confarg.exceptions import ConfargError


@dataclass
class C:
    d: dict[str, int] = field(default_factory=dict)
    u: str | dict[str, int] = ""


for argv, env in (
    (["--d", '{"x": 1,'], {}),
    ([], {"APP_D": '{"x": 1,'}),
    (["--u", '{"x": 1,'], {}),
    ([], {"APP_U": '{"x": 1,'}),
):
    try:
        print(confarg.load(C, argv=argv, env=env, env_prefix="APP_"))
    except ConfargError as e:
        print(f"{type(e).__name__}: {e}")
# expected: ConfargError: Invalid JSON for --d: Expecting property name enclosed in double quotes: line 1 column 9 (char 8)
#           ConfargError: Invalid JSON for 'APP_D': Expecting property name enclosed in double quotes: line 1 column 9 (char 8)
#           ConfargError: Invalid JSON for --u: Expecting property name enclosed in double quotes: line 1 column 9 (char 8)
#           ConfargError: Invalid JSON for 'APP_U': Expecting property name enclosed in double quotes: line 1 column 9 (char 8)
# actual:   ConfargError: Invalid JSON for --d: Expecting property name enclosed in double quotes: line 1 column 9 (char 8)
#           TypeCoercionError: Cannot construct dict at 'd': expected dict, got str '{"x": 1,'
#           ConfargError: Invalid JSON for --u: Expecting property name enclosed in double quotes: line 1 column 9 (char 8)
#           C(d={}, u='{"x": 1,')
```
