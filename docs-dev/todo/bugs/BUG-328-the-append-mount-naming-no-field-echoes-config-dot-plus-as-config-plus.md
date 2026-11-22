---
filed: 2026-11-12
where:
  - src/confarg/_pipeline.py::_load_cli_config  # spells the flag from the subpath the caller already stripped
  - tests/test_cli.py  # the REF-120 test pins `--config.+` echoed as `--config+`
effort: S
risk: low
impact: behavior  # the message names the flag as typed
severity: minor  # a misleading message, the refusal itself is right
introduced_by: [PR-209]  # feat(files): Mount a configuration file the same way from every channel
---

# BUG-328 — The append mount naming no field echoes `--config.+` as `--config+`

`--config.+ a.yaml` is refused, rightly, for naming no field to append to, but the message spells the flag `--config+`.
`_load_cli_config` receives the subpath after the flag's own `config.` has been taken off, so for `--config.+` it holds `+`, and the spelling it rebuilds, `--{config_flag}{'.' + real_subpath if real_subpath else ''}+`, has no dot to echo when `real_subpath` is empty.
A path that is not empty keeps its dot (`--config.db.+` is echoed as written), so only the empty path loses it.
The fix direction is to spell the flag from what was typed, which the caller knows (a bare `--config+` carries no subpath at all, `--config.+` carries `+`), rather than rebuild it from the stripped part.

Origin: latent, since PR-209, which made every channel mount a file the same way.
Before it the refusal was the fixed text `--{config_flag}+ requires a field path. Use --{config_flag}.fieldname+ /path/to/file.`, built from `subpath[:-1].rstrip(".")`, so it echoed `--config+` for every spelling, `--config.+` included.
PR-209 rebuilt the message to echo the path as typed (`'.' + real_subpath if real_subpath else ''`), which is right below a field and wrong at the root, because the stripped subpath cannot tell `--config+` from `--config.+`.
REF-120 (`ConfargError.append_names_no_field`) only moved the spelling into a factory, and its test loops over both flags and pins `--config+` for each, so it must change with the fix; the environment's `APP_CONFIG+` message is not affected.

```python
from dataclasses import dataclass

import confarg


@dataclass
class Cfg:
    port: int = 1


for argv in (["--config.+", "a.yaml"], ["--config+", "a.yaml"]):
    try:
        confarg.load(Cfg, argv=argv, env={})
    except confarg.exceptions.ConfargError as e:
        print(argv, "->", e)

# expected: ['--config.+', 'a.yaml'] -> --config.+ requires a field path to append to. Use --config.fieldname+ /path/to/file.
# actual:   ['--config.+', 'a.yaml'] -> --config+ requires a field path to append to. Use --config.fieldname+ /path/to/file.
#           ['--config+', 'a.yaml'] -> --config+ requires a field path to append to. Use --config.fieldname+ /path/to/file.
```
