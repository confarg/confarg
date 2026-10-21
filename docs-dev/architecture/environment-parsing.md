# Environment parsing

`_parse_env.py` turns environment variables into a nested dict, walking the same target type tree the CLI parser walks ([type-guided parsing](cli-parsing/type-guided-parsing.md)).
It sits between the two other channels in priority: above [config files](config-files/README.md), below the CLI.

- **Disabled by default** (`env_prefix=None`); see [design decisions](design-decisions/environment-variables-off-by-default.md#environment-variables-off-by-default).
- The separator defaults to `__` so single underscores stay usable in field names (`MYAPP_DB__MAX_CONNECTIONS` → `db.max_connections`).
- Segments are matched **case-insensitively** against the target type tree, because env names are conventionally upper-case; a segment matching several fields is an error.
  Case-insensitivity is the channel's **only** rule about paths.
  Each segment is spelled as the member it names — among the named members of every type the CLI channel's walk (`_parse_cli._field_types`) reaches at the spelled prefix, so every union variant and every subclass-only field — and the spelled path is then typed by `_parse_cli._resolve_field_type`, exactly as a flag of the same path is.
  The channel kept a walk of its own until REF-73, and it lagged each rule the CLI walk gained: a subclass-only field it could not see (BUG-104), a namedtuple's negative index it left uncoerced, non-struct union variants it skipped, a field below disagreeing variants it lowercased, and odd index spellings (`01`) it rewrote into ones the walk accepts.
  "Several fields" therefore counts every member the walk reaches: two variants, or a declared field and a subclass-only one, that differ only by case cannot be told apart from the environment, and the segment is an error rather than a silent pick of one of them.
- Every path starts where a flag's does: at `_parse_cli._walk_target`, the target with the [locals graft](locals.md#walk-target-graft) beside it, which segments are spelled, typed, cast and checked against.
  The real target only classifies the root.
  The channel walked the bare target until BUG-115, so a variable could take a path no flag can.
  The locals namespace is one of the members a root segment is spelled among, so a field that differs from a namespace name only by case (`Locals`) is ambiguous here, where the CLI tells `--Locals` from `--locals.x` apart.
  Before BUG-115 such a field silently won, and the namespace could not be reached from the environment.
- A **non-struct root** is [set whole](cli-parsing/cli-prefix.md#a-non-struct-root-is-set-whole): by the bare `<PREFIX>` variable, or by its `<PREFIX>JSON` cast.
  Every other variable names a path below the root, and no flag reaches one, so the first-segment check below warns about it and ignores it.
  On a struct-like root the bare `<PREFIX>` names nothing, and `<PREFIX>+` and `<PREFIX>-` patch no root of any kind: each is warned about with the cause the CLI refuses `--<prefix>` and `--<prefix>+` with ([the bare prefix names the root](cli-parsing/cli-prefix.md#the-bare-prefix-names-the-root), BUG-183, BUG-178).
  The locals namespace beside the root is the exception: `<PREFIX>LOCALS__N` reaches it, as `--<prefix>.locals.n` does.
  Until BUG-115 a branch of its own wrote every prefixed variable to `__root__`, so `MYAPP_DEBUG` replaced the root, and when several were set the mapping's order chose the winner.
- A segment that names no member but names the union tag resolves to the tag's **exact spelling**, whatever case the variable spelled it in (BUG-101): the walks downstream — the mount-subpath check, `build()` — compare the tag exactly, so a lowercased custom tag such as `Kind` would be warned away and dropped while the CLI channel's `--Kind` merged.
  A member that matched case-insensitively always wins over the tag, which is what the default lowercase `class` tag already did; the CLI can tell `--Kind` (tag) from `--kind` (field) by case, and the env channel — where every spelling collapses to one — settles that collision on the field.
  The exact collision settles on the field on every channel now, the walk and construction reading the key as the field's value rather than a class path (BUG-102, [CLI parsing](cli-parsing/casts-and-reserved-words.md#real-field-wins)).
  The one decision-maker is `_env_spelling`, so the field variables, deletes, casts and config subpaths all resolve through it.
- Values starting with `[` or `{` are parsed as JSON only when the target type can accept a list or an object; otherwise they are ordinary tokens.
  Which types those are is not this channel's question: `{` defers to `_parse_cli._accepts_object_value`, the one predicate the CLI whole-value flag consults ([whole-value flags](cli-adapters/whole-value-flags.md#whole-value-flags)), and `[` to `_types._is_seq_variant` plus `_union_has_seq_variant`.
  Asking again here is what let a plain class take the blob from the environment while the CLI refused it (BUG-39, closed): a *struct* is either spelling of one, because construction takes a dataclass and a plain class apart the same way.
  Optionality does not change the answer either — `dict[str, str] | None` decodes what `dict[str, str]` decodes ([design decisions](design-decisions/optionality-and-whole-values.md#optionality-does-not-change-what-a-whole-value-accepts)).
- `<PREFIX>…__json` mirrors the CLI `.json` cast, including "real field wins", a hard error on invalid JSON, and a decoded value that is data, as a JSON whole value is too ([design decisions](design-decisions/a-decoded-value-is-data.md#a-decoded-value-is-data)).
  `<PREFIX>JSON` is the root form: it injects a whole config, folded in **under** the per-field env vars exactly as root `--json` sits under the field flags ([CLI parsing](cli-parsing/casts-and-reserved-words.md#force-casts)).
  Whether a trailing `json` is a cast at all is decided by the canonical `detect_force_cast`, not by a second rule in `_parse_env`.
  Asked of the walk target, so a dict root's `<PREFIX>JSON` is its cast, as `--<prefix>.json` is: no key of a root set whole is a member for a real one to win.
  On a scalar root the plain `<PREFIX>` variable wins over `<PREFIX>JSON`, whatever the mapping's order (REF-44): the plain value refines the cast, as a per-field variable does on a struct root.
  That is one case of the order every variable is applied in ([below](#the-broader-variable-applies-first)).
- `FOO__BAR-` / `FOO__ITEMS__1-` are deletes, mirroring `--bar-` / `--items.1-`.
  A delete's path, its `-` dropped, is spelled, typed and checked exactly as a value variable's of the same path: the first-segment check and the refusal below a sequence, both below.
- `FOO__ITEMS+` appends, mirroring `--items+`, at any depth (FEAT-18, [design decisions](design-decisions/plus-is-a-merge-operator.md#the-environment-spells-it-in-the-variables-name)).
  Its path is checked as a delete's is, and what it may append to and how its value becomes items are the flag's: `_parse_cli._appended_element_type` refuses a path holding no list, set or variadic tuple, and `_parse_cli._collect_append_items` reads the value as the flag's single token, a JSON array several items.
  `CONFIG__ITEMS+` appends a fragment's items, as `--config.items+` does ([mounting](config-files/mounting.md#mounting)).
- `<PREFIX>CONFIG[__SUBPATH]` are file pointers, collected and loaded by the pipeline.
  Their value is read as an `__include__` value, so `<PREFIX>CONFIG__USERS={"path": "users.csv", "orient": "columns"}` says in the environment what a file says with a mapping ([mounting](config-files/mounting.md#mounting)).
  The variable named by `env_config` is removed from field parsing.
- An unknown first segment emits `ConfargWarning` and the variable is ignored, whereas an unknown CLI flag is an error.
  "Unknown" is not this channel's question to answer: the check asks the walk target the CLI's own `_parse_cli._path_unknown`, so a first segment is warned about exactly when its flag would be refused.
  The union tag and a subclass-only field name a member on a struct root — the tag was warned away and dropped before BUG-90, while the CLI and file channels accepted the same configuration — and nothing names one below a non-struct root, the tag included (BUG-115).
  The check asked `_segment_names_real_field` of the bare target until then, which counts every key of a dict root and the tag of any root as a member.
  A delete is checked as the value variable of the path it deletes: until BUG-182 its branch ended ahead of the check, so `APP_NAEM-` was dropped without a word while `APP_NAEM=y` was warned about and `--naem-` refused.
  *(inferred)* The environment is ambient and shared with other software, while argv is an explicit request; a stray variable should not stop the program.
  Tests can escalate the warning with `warnings.filterwarnings("error", …)`.
- An unknown segment *below* the first is stored as spelled and left for `build()` to refuse (`APP_SUB__ZZ` → "Unknown field(s)"), except below a sequence: there a segment naming no element — no index as `str()` writes one, no namedtuple field — is refused at parse (`_sequence_refusal`), delete included, because stored it would reach the merge as one of its own list-patch keys, `APP_XS__+` an append and `APP_PAIR__*=12` the base `(1, 2)` ([CLI parsing](cli-parsing/collection-patches.md#a-segment-below-a-sequence-is-an-index), BUG-170).
  A variable that deep was never ambient noise to drop: it already stopped the program at `build()`.

## A naming anywhere in it types a variable

A variable below a node naming a class is typed by that class (`_parse_env._env_namings`): the environment's own opener, tag, `{…}` value or shorthand at the node, wherever it sorts, else the config level's, which the pipeline reads first.
A variable's segments below it are spelled against that class's members too ([design decisions](design-decisions/a-node-types-its-keys-by-the-class-it-names.md#which-naming-types-a-key)).

## The broader variable applies first

The CLI settles two flags whose paths nest by "last typed wins".
The environment has no typing order — a mapping's iteration order is an accident of how it was built — so `_parse_env` gives it one before writing anything: `_parse_env._env_order` sorts the variables by the depth of the path each one writes, then, at one path, a delete before a `json` cast before a plain value before an append, then by name.
A deeper variable therefore always refines a broader one, exactly as its flag does when typed after the broader flag:

| variables, either order | as the CLI's | merges to |
|---|---|---|
| `APP_USERS='["q", "r"]'`, `APP_USERS__0=x` | `--users '["q", "r"]' --users.0 x` | `[x, r]` |
| `APP_DB__json='{"host": "h"}'`, `APP_DB__PORT=2` | `--db.json '{"host": "h"}' --db.port 2` | `host=h, port=2` |
| `APP_USERS-`, `APP_USERS__0-` | `--users- --users.0-` | error: no base list ([deep merge](pipeline/deep-merge.md#an-op-after-a-whole-field-delete-has-nothing-below-it)) |
| `APP_DB=oops`, `APP_DB__HOST=db1` | `--db oops --db.host db1` | `{host: db1}` |
| `APP_USERS='["q"]'`, `APP_USERS+=r` | `--users '["q"]' --users+ r` | `[q, r]` |
| `<PREFIX>JSON`, `<PREFIX>` on a scalar root | `--json … --<prefix> …` | the plain value |

The depth of a cast is that of the path it writes, its parent's: `_env_cast` answers both the order and the write, so the two cannot disagree on whether a trailing `json` is a cast.
File pointers are not in this order: the pipeline loads them, sorted by subpath ([merge order](pipeline/merge-order.md#source-precedence)).
Until BUG-116 the variables were written in the mapping's order, and every pair above resolved one way or the other depending on how the environment was built; REF-44 had settled the root case alone.
Why this order and not another is in [design decisions](design-decisions/the-broader-environment-variable-applies-first.md#the-broader-environment-variable-applies-first).
