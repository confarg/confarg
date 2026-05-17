---
filed: 2026-10-06
where:
  - src/confarg/cli/cyclopts/_register.py::_spec_to_inspect_param
  - src/confarg/cli/cyclopts/_context.py::_merge_app
effort: M
risk: medium
impact: behavior
severity: major
needs_design: true
introduced_by: [PR-72]  # fix: Close CLI-adapter parity gaps, which registered dict-key flags on cyclopts
---

# BUG-180 — Cyclopts refuses a flag whose name ends in a star

Cyclopts reads a trailing `*` in an option name as its own flattening syntax (`Parameter(name="*")`, `"foo.*"`) and strips it, with the dots before it, in `resolve_parameter_name_helper`.
So the dict-key flag `--d.*` registers as `--d`, `--d.a*` as `--d.a`, and cyclopts refuses the flag the user typed as an unknown option.
The other four front-ends build the key.
BUG-173's invalid parameter name hid this until it was fixed.
No `name` spelling survives the strip, so the fix needs a design: register such a flag under a name cyclopts keeps and rewrite its occurrences in the argv cyclopts parses, as `merge_app` already drops bare occurrences ([a flag that stands bare](../../architecture/cli-adapters/a-flag-that-stands-bare.md#a-flag-that-stands-bare)), or refuse it with confarg's own error and record the limitation.
The contract case `test_index_below_a_sequence_and_key_of_a_dict_variant_are_kept[cyclopts-key-of-a-dict-variant]` xfails strictly on cyclopts for this.

Origin: latent since PR-72, a bug fix that first registered dict-subkey flags on the adapters.
Before it no adapter accepted `--d.<key>` at all; PR-72 closed that gap and missed this spelling on cyclopts (bisected: cyclopts refuses `--d.*` before PR-72, crashes on it from PR-72).
The crash was the invalid parameter name `d__*` (BUG-173), and BUG-173's fix uncovered cyclopts' own star syntax beneath it.
BUG-198 shares this origin.

```python
from dataclasses import dataclass, field

import cyclopts

import confarg
from confarg.cli.cyclopts import from_app, populate_app


@dataclass
class Cfg:
    d: dict[str, int] = field(default_factory=dict)


for key in ("*", "a*"):
    argv = [f"--d.{key}", "1"]
    print(key, "vanilla:", confarg.load(Cfg, argv=argv, env={}))
    app = cyclopts.App(exit_on_error=False, print_error=False)
    populate_app(Cfg, app, argv=argv)
    try:
        print(key, "cyclopts:", from_app(Cfg, app, argv=argv))
    except cyclopts.CycloptsError as e:
        print(key, "cyclopts:", type(e).__name__, e)

# expected: cyclopts builds Cfg(d={'*': 1}) and Cfg(d={'a*': 1}), as vanilla does
# actual:
#   * vanilla: Cfg(d={'*': 1})
#   * cyclopts: UnknownOptionError Unknown option: --d.*. Did you mean --d?
#   a* vanilla: Cfg(d={'a*': 1})
#   a* cyclopts: UnknownOptionError Unknown option: --d.a*. Did you mean --d.a?
```
