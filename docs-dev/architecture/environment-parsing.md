# Environment parsing

`_parse_env.py` turns environment variables into a nested dict, walking the same target type
tree the CLI parser walks ([type-guided parsing](cli-parsing/type-guided-parsing.md)). It sits
between the two other channels in priority: above
[config files](config-files/README.md), below the CLI.

- **Disabled by default** (`env_prefix=None`); see
  [design decisions](design-decisions/environment-variables-off-by-default.md#environment-variables-off-by-default).
- The separator defaults to `__` so single underscores stay usable in field names
  (`MYAPP_DB__MAX_CONNECTIONS` → `db.max_connections`).
- Segments are matched **case-insensitively** against the target type tree, because env
  names are conventionally upper-case; a segment matching several fields is an error.
- A segment that names no member but names the union tag resolves to the tag's **exact
  spelling**, whatever case the variable spelled it in (BUG-101): the walks downstream —
  the mount-subpath check, `build()` — compare the tag exactly, so a lowercased custom tag
  such as `Kind` would be warned away and dropped while the CLI channel's `--Kind` merged.
  A member that matched case-insensitively always wins over the tag, which is what the
  default lowercase `class` tag already did; the CLI can tell `--Kind` (tag) from
  `--kind` (field) by case, and the env channel — where every spelling collapses to one —
  settles that collision on the field. The exact collision settles on the field on every
  channel now, the walk and construction reading the key as the field's value rather than a
  class path (BUG-102,
  [CLI parsing](cli-parsing/casts-and-reserved-words.md#real-field-wins)).
  The one decision-maker is `_match_env_part`, so the
  field variables, deletes, casts and config subpaths all resolve through it.
- Values starting with `[` or `{` are parsed as JSON only when the target type can accept a
  list or an object; otherwise they are ordinary tokens. Which types those are is not this
  channel's question: `{` defers to `_parse_cli._accepts_object_value`, the one predicate the
  CLI whole-value flag consults ([04](cli-adapters/whole-value-flags.md#whole-value-flags)), and `[` to
  `_types._is_seq_variant` plus `_union_has_seq_variant`. Asking again here is what let a
  plain class take the blob from the environment while the CLI refused it (BUG-39, closed):
  a *struct* is either spelling of one, because construction takes a dataclass and a plain
  class apart the same way. Optionality does not change the answer either —
  `dict[str, str] | None` decodes what `dict[str, str]` decodes
  ([design decisions](design-decisions/optionality-and-whole-values.md#optionality-does-not-change-what-a-whole-value-accepts)).
- `<PREFIX>…__json` mirrors the CLI `.json` cast, including "real field wins" and a hard
  error on invalid JSON. `<PREFIX>JSON` is the root form: it injects a whole config, folded
  in **under** the per-field env vars exactly as root `--json` sits under the field flags
  ([CLI parsing](cli-parsing/casts-and-reserved-words.md#force-casts)). Whether a trailing `json` is a cast at all is
  decided by the canonical `detect_force_cast`, not by a second rule in `_parse_env`.
- `FOO__BAR-` / `FOO__ITEMS__1-` are deletes, mirroring `--bar-` / `--items.1-`.
- `<PREFIX>CONFIG[__SUBPATH]` are file pointers, collected and loaded by the pipeline. Their
  value is read as an `__include__` value, so `<PREFIX>CONFIG__USERS={"path": "users.csv",
  "orient": "columns"}` says in the environment what a file says with a mapping
  ([mounting](config-files/mounting.md#mounting)). The variable named by `env_config` is removed from field parsing.
- An unknown first segment emits `ConfargWarning` and the variable is ignored, whereas an
  unknown CLI flag is an error. "Real member" is not this channel's question to answer: the
  check defers to the canonical `_parse_cli._segment_names_real_field`
  ([CLI parsing](cli-parsing/casts-and-reserved-words.md#real-field-wins)), so the union tag
  and a subclass-only field name a member — the tag was warned away and dropped before
  BUG-90, while the CLI and file channels accepted the same configuration. *(inferred)* The
  environment is ambient and shared with other software, while argv is an explicit request; a
  stray variable should not stop the program. Tests can escalate the warning with
  `warnings.filterwarnings("error", …)`.
