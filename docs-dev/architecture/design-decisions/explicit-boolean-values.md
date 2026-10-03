# Explicit boolean values

Booleans take a value (`--verbose true`), not `--flag`/`--no-flag`. A bool then behaves like
every other scalar in every channel, with no special parsing or merge rule, and a CLI value can
override a file value in either direction. Cost: less idiomatic for CLI-only users. Precedent:
jsonargparse accepts explicit `true/false` values.
