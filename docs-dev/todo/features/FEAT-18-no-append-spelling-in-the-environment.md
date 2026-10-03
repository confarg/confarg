# FEAT-18 — The environment channel has no append spelling

**Where:** `src/confarg/_parse_env.py` · **Filed:** 2026-09-21
**Effort:** M *(design pass; implementation not sized)* · **Risk:** low · **Impact:** behavior

Argv and config files both extend a list with the same `+` suffix — `--input+ 42`, `input+: [42]`,
`--config.dbs+ other.yaml`. The environment can only replace one. `MYAPP_USERS+` is not matched as
an append: it is treated as an unknown first segment, warned about and dropped
([environment-parsing.md#environment-parsing](../../architecture/environment-parsing.md#environment-parsing)).

The config-flag route is worse than dropped: `MYAPP_CONFIG__DBS+` is intercepted before the
field walk, so the `+` never reaches that warning — it survives as a literal key segment and
the fragment is mounted at `dbs+`, silently producing `{"dbs": {"+": [...]}}` and surfacing at
`build()` as an unknown field. Whatever spelling this ticket settles on should reach the
config-flag interception too (observed 2026-09-29, while fixing BUG-50).

Portability does not explain the gap, which is why it is filed rather than recorded as a
limitation and closed: the *delete* suffix made the crossing (`MYAPP_USERS-` empties the list,
`MYAPP_USERS__0-` drops an element), and `-` is no more exportable from a POSIX shell than `+` is.
Env names come from a mapping confarg is handed, not from shell syntax, so whatever spelling the
delete gets away with an append could get away with too. Appends were simply never wired up.

Two shapes to weigh, neither obviously right:

- **Keep the `+` suffix**, `MYAPP_USERS+`, for one vocabulary across all three channels
  ([design-decisions/plus-is-a-merge-operator.md#the--suffix-is-a-merge-operator-not-a-list-spelling](../../architecture/design-decisions/plus-is-a-merge-operator.md#the--suffix-is-a-merge-operator-not-a-list-spelling)).
  Consistent with the delete already there, and awkward to set from a shell — as the delete
  already is.
- **A value-side marker**, `MYAPP_USERS='@merge ["x"]'`, the shape dynaconf chose. It keeps
  variable names shell-friendly, but introduces a second vocabulary the CLI and file channels do
  not share, needs an escape for a literal value that starts with the marker, and would leave the
  delete spelled one way and the append another.

The prior question is whether this is worth closing at all: the environment is where a whole value
is spelled comfortably, and the CLI is where a configuration is tweaked
([design-decisions/divergence-leans-to-the-backend.md#a-divergence-leans-towards-the-affected-backends-own-idiom](../../architecture/design-decisions/divergence-leans-to-the-backend.md#a-divergence-leans-towards-the-affected-backends-own-idiom)).
Recording the gap as a limitation and declining it is a legitimate outcome.
