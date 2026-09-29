# Environment variables off by default

`env_prefix=None` disables env parsing. Environment variables are global and shared by every
process, so reading them without an explicit, app-specific prefix is unsafe in shared
environments; `""` (read all) is opt-in, not the default. Cost: one extra argument for the
common case. Precedent: pydantic-settings and Dynaconf both scope by prefix.
