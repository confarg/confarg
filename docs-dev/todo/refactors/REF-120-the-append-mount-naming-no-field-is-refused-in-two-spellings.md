---
filed: 2026-10-26
where:
  - src/confarg/_pipeline.py::_load_cli_config  # `--config+`
  - src/confarg/_parse_env.py::_refuse_root_config_append  # `APP_CONFIG+`
  - src/confarg/exceptions.py
effort: S
risk: low
impact: none
severity: trivial
---

# REF-120 — The append mount naming no field is refused in two spellings

`--config+ a.yaml` and `APP_CONFIG+=a.yaml` name no field to append to, and each channel builds its own `ConfargError` inline: `--config+ requires a field path to append to. Use --config.fieldname+ /path/to/file.` and `Environment variable 'APP_CONFIG+' requires a field path to append to. Use APP_CONFIG__<FIELD>+=/path/to/file.`.
The reason is one and only the spellings differ, so it belongs in one factory on the exception that takes the spelled key and its remedy, as the refusals [living on their exception](../../architecture/design-decisions/messages-live-on-exceptions.md#a-user-facing-message-lives-on-the-exception-that-raises-it) do.
Both checks run before `_files._load_mount`, which both channels reach; the factory is the shared part, the spelling of each channel's key stays with it.
