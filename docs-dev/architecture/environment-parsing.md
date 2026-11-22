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
  The bare variable is read as a field variable of the root's type is, by `_store_env_value` at `__root__`: `APP_='[1, 2]'` sets a `list[int]` root as `APP_XS='[1, 2]'` sets such a field, where it was kept as text that construction refused (BUG-177).
  Every other variable names a path below the root, and no flag reaches one, so the first-segment check below warns about it and ignores it.
  On a struct-like root the bare `<PREFIX>` names nothing, and `<PREFIX>+` and `<PREFIX>-` patch no root of any kind: each is warned about with the cause the CLI refuses `--<prefix>` and `--<prefix>+` with ([the bare prefix names the root](cli-parsing/cli-prefix.md#the-bare-prefix-names-the-root), BUG-183, BUG-178).
  The locals namespace beside the root is the exception: `<PREFIX>LOCALS__N` reaches it, as `--<prefix>.locals.n` does.
  Until BUG-115 a branch of its own wrote every prefixed variable to `__root__`, so `MYAPP_DEBUG` replaced the root, and when several were set the mapping's order chose the winner.
- A segment that names no member but names the class key resolves to `class`, whatever case the variable spelled it in (BUG-101).
  A member that matched case-insensitively wins over it: a field `Class`, which is no keyword, takes `APP_DB__CLASS`, where the CLI tells `--db.Class` (field) from `--db.class` (key) by case, since the env channel collapses every spelling to one.
  The one decision-maker is `_env_spelling`, so the field variables, deletes, casts and config subpaths all resolve through it.
- Values starting with `[` or `{` are read as a flag's are ([token consumption](cli-parsing/token-consumption.md#a-json-led-value-is-read-by-its-type)): decoded where the type reads the list or the object they open, refused naming the variable where they are no JSON and the type reads nothing else, text otherwise.
  Which types those are is not this channel's question: `_store_env_value` asks `_parse_cli._takes_json` and `_parse_cli._read_json`, the decision-makers the CLI's whole values and items ask, whose object half the whole-value flag consults too ([whole-value flags](cli-adapters/whole-value-flags.md#whole-value-flags)).
  Until BUG-323 a value that was no JSON was text here wherever argv refused it.
  Asking again here is what let a plain class take the blob from the environment while the CLI refused it (BUG-39, closed): a *struct* is either spelling of one, because construction takes a dataclass and a plain class apart the same way.
  Optionality does not change the answer either — `dict[str, str] | None` decodes what `dict[str, str]` decodes ([design decisions](design-decisions/optionality-and-whole-values.md#optionality-does-not-change-what-a-whole-value-accepts)).
- `<PREFIX>…__str`, `__int`, `__float`, `__bool` and `__json` mirror the CLI's `.<cast>` suffixes, in any case (`MYAPP_VALUE__STR=true`), and store what the flag stores: a pin for a scalar cast, the decoded data for `json`, with a hard error on invalid JSON and a decoded value that is data, as a JSON whole value is too ([design decisions](design-decisions/a-decoded-value-is-data.md#a-decoded-value-is-data), [casts](#a-variable-spells-every-cast-its-flag-spells)).
  `<PREFIX>JSON` is the root form: it injects a whole config, folded in **under** the per-field env vars exactly as root `--json` sits under the field flags ([CLI parsing](cli-parsing/casts-and-reserved-words.md#force-casts)).
  Whether a trailing segment is a cast at all is decided by the canonical `detect_force_cast`, not by a second rule in `_parse_env`.
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
  The class key and a subclass-only field name a member on a struct root — the class key was warned away and dropped before BUG-90, while the CLI and file channels accepted the same configuration — and nothing names one below a non-struct root, the class key included (BUG-115).
  The check asked `_segment_names_real_field` of the bare target until then, which counts every key of a dict root and the class key of any root as a member.
  A delete is checked as the value variable of the path it deletes: until BUG-182 its branch ended ahead of the check, so `APP_NAEM-` was dropped without a word while `APP_NAEM=y` was warned about and `--naem-` refused.
  *(inferred)* The environment is ambient and shared with other software, while argv is an explicit request; a stray variable should not stop the program.
  Tests can escalate the warning with `warnings.filterwarnings("error", …)`.
- A path *below* the first segment that no flag reaches is refused at parse, delete included ([below](#a-path-no-flag-reaches-is-refused-below-the-first-segment)).

## A path no flag reaches is refused below the first segment

Once its first segment names a member, a variable whose path names nothing a flag writes is refused with `ConfargError`, for the cause `_parse_cli._unreached` gives its flag (BUG-265):

| variable | its flag | refused because |
|---|---|---|
| `APP_PORT__`, `APP_PORT__+`, `APP_PORT__-` | `--port.`, `--port.+`, `--port.-` | missing field name after `APP_PORT__` |
| `APP_XS__ZZ` | `--xs.zz` | segment `zz` names no element of `xs` |
| `APP_PORT__ZZ`, `APP_DB__ZZ`, `APP_PORT__X-` | `--port.zz`, `--db.zz`, `--port.x-` | field `port.zz` (`db.zz`, `port.x`) not found |

A key path below a dict, a path below an `Any` or a callable's spec, and a subclass's field all name something, as their flags do: `APP_D__=1` sets the key `''` of a dict, as `--d. 1` does.

Such a variable was stored as spelled and left for `build()`, which blamed the value below a leaf (`Cannot coerce dict {'': '1'} to int`) or named a field the CLI would have refused with its cause; and a delete of one was dropped without a word, since a delete of a key no layer holds deletes nothing.
Only a segment below a sequence was refused at parse (BUG-170), because stored it reaches the merge as one of its own list-patch keys: `APP_XS__+` an append, `APP_PAIR__*=12` the base `(1, 2)`.
A variable that deep was never ambient noise to warn about and drop, as an unknown first segment is: below a member the program stopped at `build()` already, so refusing it at parse with the cause loses nothing a stray variable could rely on, where a warning would have let a typo build the default.
The cause is spelled with one text the CLI shares (`exceptions._missing_field_name`, `_no_element`, `_field_not_found`), so `--xs.zz` is told what `APP_XS__ZZ` is, and `--port.-` misses its name, as `--port.+` always did.

## A naming anywhere in it types a variable

A variable below a node naming a class is typed by that class (`_parse_env._env_namings`): the environment's own opener, tag, `{…}` value or shorthand at the node, wherever it sorts, else the config level's, which the pipeline reads first.
A variable's segments below it are spelled against that class's members too ([design decisions](design-decisions/a-node-types-its-keys-by-the-class-it-names.md#which-naming-types-a-key)).
A cast variable names at the path it writes: a `json` cast its decoded object or list, so `APP_U__JSON='{"class": "B"}'` types `APP_U__X` by `B` as `--u.json` types `--u.x`; a scalar cast names nothing, as a scalar value names nothing.
Until BUG-324 a `json` cast's object was recorded one segment too deep, at `u.json`, and typed nothing.

## A variable spells every cast its flag spells

`_parse_env._env_cast` is the channel's one answer to "is this variable a cast?", for every name of `_cast.FORCE_CAST_NAMES`, and the namings scan, the order and the write all ask it.
It spells every segment first, the last one included, then asks the canonical `detect_force_cast` of the spelled path, with what the data names at each node, as a flag's cast is asked with `ctx.naming`; the value stored is the one `_cast.resolve_forced_value` produces for the flag.
So a variable and a flag of one path admit and pin the same casts (BUG-324), and three consequences follow from the one decision-maker:

- **A member of any case wins.**
  Spelling the last segment first makes a member the cast word names case-insensitively (a field `Json`, `Str`) the variable's own, as a member wins over the class key ([above](#environment-parsing)).
  The CLI tells `--n.Json` (field) from `--n.json` (cast) apart by case, which the environment cannot; a field named exactly like the cast wins on both channels by [real field wins](cli-parsing/casts-and-reserved-words.md#real-field-wins).
  Until BUG-324 the channel asked about the literal `json`, so `APP_N__JSON=5` was the cast even where `n` has a field `Json`, and a root `APP_JSON` beside a root field `Json` injected the whole configuration.
- **Below an `Any`, a cast word is a cast** (a `config` change of BUG-324): `APP_A__STR=5` builds `'5'` where it built `{'str': '5'}`, as `--a.str 5` builds `'5'` and as `APP_A__JSON` was already the `json` cast there.
  A dict key spelled like a cast stays a key (`APP_D__STR=5` sets the key `str`), since every key of a dict is a member.
- **The namings narrow it.**
  Below a node whose tag or opener names a class, a cast that class does not hold is no cast, and the variable is refused at parse with its flag's cause: `APP_U__CLASS=B` beside `APP_U__X__STR` where `B.x` is an `int`, or `APP_F__CALL=…` beside `APP_F__X__JSON`, whose `x` no argument spells (`field 'f.x.json' not found`).
  Until BUG-324 the `json` cast was asked without them, and construction refused such a variable later with another message.

A nested cast is written as the flag's is: a callable shorthand above it is opened into the spec it refines (`APP_F=mod.greet` beside `APP_F__ARGS__X__STR=5`), and a node it restates is emptied, where until BUG-324 the shorthand stayed a string the cast could not be written into.
A scalar cast's value is a `_Pinned`, which resolution does not enter: `APP_F__STR='at ${x}'` builds the text `at ${x}`, as `--f.str 'at ${x}'` does ([BUG-327](../todo/bugs/BUG-327-an-argv-scalar-cast-leaves-its-expression-unresolved.md)).

## The broader variable applies first

The CLI settles two flags whose paths nest by "last typed wins".
The environment has no typing order — a mapping's iteration order is an accident of how it was built — so `_parse_env` gives it one before writing anything: `_parse_env._env_order` sorts the variables by the depth of the path each one writes, then, at one path, a delete before a cast before a plain value before an append, then by name.
A deeper variable therefore always refines a broader one, exactly as its flag does when typed after the broader flag:

| variables, either order | as the CLI's | merges to |
|---|---|---|
| `APP_USERS='["q", "r"]'`, `APP_USERS__0=x` | `--users '["q", "r"]' --users.0 x` | `[x, r]` |
| `APP_DB__json='{"host": "h"}'`, `APP_DB__PORT=2` | `--db.json '{"host": "h"}' --db.port 2` | `host=h, port=2` |
| `APP_USERS-`, `APP_USERS__0-` | `--users- --users.0-` | error: no base list ([deep merge](pipeline/deep-merge.md#an-op-after-a-whole-field-delete-has-nothing-below-it)) |
| `APP_DB=oops`, `APP_DB__HOST=db1` | `--db oops --db.host db1` | `{host: db1}` |
| `APP_USERS='["q"]'`, `APP_USERS+=r` | `--users '["q"]' --users+ r` | `[q, r]` |
| `<PREFIX>JSON`, `<PREFIX>` on a scalar root | `--json … --<prefix> …` | the plain value |
| `APP_S__STR=2`, `APP_S=1` | `--s.str 2 --s 1` | `1` |

The depth of a cast is that of the path it writes, its parent's: `_env_cast` answers both the order and the write, so the two cannot disagree on whether a trailing segment is a cast.
The namings scan sorts the variables before any naming is known, so it orders them without one; the writes are sorted again with the namings it collected, which is what the write asks `_env_cast` with.
File pointers are not in this order: the pipeline loads them, sorted by subpath ([merge order](pipeline/merge-order.md#source-precedence)).
Until BUG-116 the variables were written in the mapping's order, and every pair above resolved one way or the other depending on how the environment was built; REF-44 had settled the root case alone.
Why this order and not another is in [design decisions](design-decisions/the-broader-environment-variable-applies-first.md#the-broader-environment-variable-applies-first).
