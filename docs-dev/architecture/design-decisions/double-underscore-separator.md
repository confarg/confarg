# Double underscore separator

`__` splits nesting so single underscores remain usable in names. Precedents:
pydantic-settings `env_nested_delimiter="__"`, Dynaconf `__`. Side effect: dunder keys cannot be
expressed in env ([config files](../config-files/reserved-keys.md#reserved-file-only-keys)).
