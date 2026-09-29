# Type-guided parsing

Argv is not parsed as generic `key=value` pairs: each dotted path is resolved against the
target type (`_resolve_field_type`) to decide whether a segment names a field, indexes a
sequence, keys a dict, enters a callable spec, or is a cast. That is what lets
`--db.hosts.0.port 5432` produce the right nested structure and what lets values be coerced
eagerly. Env parsing walks the same type tree ([environment parsing](../environment-parsing.md#environment-parsing)).

An unknown flag is an error (`UnknownArgumentError`); an unresolvable path under a dict is
accepted as a dict key.

The one path not resolved *while* it is parsed is the config flag's subpath: the flag is
intercepted before field lookup
([design decisions](../design-decisions/mount-keyword-per-channel.md#the-mount-keyword-is-spelled-per-channel)), so the check runs
once the interception is over (`_check_mount_subpath`, one walk shared with the environment
channel and the adapters' rescan). A subpath that names no node — a misspelled field, or a
descent through a scalar — is an error at parse time, not a silent mount at an invented key
that surfaces much later as an unknown-field error from `build()` (BUG-50, closed). What the
node *holds* is still not the scan's question: a path is accepted at any depth it resolves to,
because whether the fragment fits is the mount's call.
