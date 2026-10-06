# Framework specifics

- **argparse**: value-less flags become `store_true` (argparse forbids `nargs=0` on store);
  argument groups from `FlagSpec.group`; `make_parser` defaults `allow_abbrev=False` so
  adding a field later cannot silently change what an abbreviated flag means.
- **click**: options cannot take `nargs=-1`, so `"*"` maps to `multiple=True` — hence the
  repeated-flag list syntax; no argument groups; `_ConfargOption` allows dotted names; the
  command callback is wrapped to strip confarg parameters from its kwargs.
- **typer**: everything click's entry says, since the option class is a fork of click's —
  `multiple=True` for `"*"`, no argument groups, dotted names via the shared mixin. What
  differs: `autocompletion` rather than the deprecated `shell_complete`, and
  `populate_command` takes the command `typer.main.get_command(app)` returns, not the
  `typer.Typer` app ([the clicklike seam](clicklike-seam.md#the-clicklike-seam)).
- **cyclopts**: flags become a synthetic default function whose `inspect.Signature` holds one
  keyword-only parameter per flag; `_pyname` maps flag names to distinct identifiers and a
  name map restores them ([below](#cyclopts-parameter-names)); metadata is kept in
  module-level `_app_meta` keyed by `id(app)` (App is unhashable) and holding a reference to
  the app so the id cannot be reused after GC;
  `negative=()` suppresses `--no-*`/`--empty-*`; there is no metavar, so the type name is
  prefixed to the help text. Cyclopts accepts both list syntaxes.

## Cyclopts parameter names

A flag name is a path, and a path segment below a dict is any key the user types: `--d.x[0].k`,
`--d.a/b.k`, `--d.a b.k`. `inspect.Parameter` accepts only an identifier, so `_pyname` escapes
every character outside ASCII letters and digits, and, since the name map is a dict keyed by the
identifier, it must also keep distinct flags distinct: two flags given one name register as one
parameter, and cyclopts refuses the second as an unknown option. It does both the way JNI's
native-method mangling and GHC's Z-encoding turn arbitrary names into C symbols, by escaping the
escape character itself: `_` doubles to `__`, and any other character spells its code point
`_<hex>_`, so `--db.host` is `db_2e_host` and `--db_host` is `db__host`. Read left to right, each
`_` opens either a doubled `_` or a hexadecimal escape closed by the next `_`, so an identifier
decodes to one name only. A leading digit and the first letter of a keyword are escaped the same
way (`1x` is `_31_x`, `class` is `_63_lass`), which keeps the mapping a pure function of the name
(BUG-173).

Rejected: **a reserved token per non-identifier character** — `.` as `__`, `+` as `__append_`,
`-` as `__delete_`, every other character left as it was. A key holding any other character left
the name invalid, and with `_` unescaped a key could spell a separator's token: `--d.a__b.c` and
`--d.a.b__c` were both `d__a__b__c`.

Rejected: **a positional name** (`p0`, `p1`, …), unique by construction. It would work as well,
the name never reaching the user, but it ties a parameter's name to registration order, so a
debugger or a traceback shows `p17` where the escape still reads as the flag.
